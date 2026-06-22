"""PR2 create_campaign — 정책·writer 게이팅·executor 디스패치·재생성 패키징 (옵션 A).

신규 캠페인은 대상 id가 없어 CampaignConfig를 evidence_metrics에 싣는다(스키마 무변경).
실제 Meta 호출은 일어나지 않는다 (MockTransport / FakeWriter).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from domain.management.adapters.meta.client import MetaClient
from domain.management.adapters.meta.writer import MetaAdsWriter
from domain.management.agents.regeneration import (
    CreativeCandidate,
    RemediationAgent,
    RemediationContext,
    label_action_tier,
)
from domain.management.contracts.enums import ActionTier, AnomalyType, ExecutionMode, ResultStatus
from domain.management.contracts.policy import TIER_POLICY
from domain.management.contracts.schemas import (
    CampaignConfig,
    DiagnosisResult,
    verify_proposal_hash,
)
from tests.management.helpers import (
    NOW,
    POLICY_VERSION,
    STATE_VERSION,
    FakeWriter,
    build_executor,
    make_action,
    make_proposal,
)


def _config(account: str = "111", campaign: str = "camp-new-1") -> CampaignConfig:
    return CampaignConfig(
        campaign_id=campaign,
        tenant_id="org-1111",
        ad_account_id=account,
        daily_budget_krw=50_000,
        start_at=NOW,
        end_at=NOW + timedelta(days=7),
    )


# ── 정책 ─────────────────────────────────────────────────────────


def test_create_campaign_is_tier3():
    assert TIER_POLICY["CREATE_CAMPAIGN"] is ActionTier.TIER_3
    assert label_action_tier("CREATE_CAMPAIGN") is ActionTier.TIER_3


# ── writer 게이팅 ────────────────────────────────────────────────


def test_create_campaign_dry_run_does_not_send():
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"id": "23842"})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN, client=client)
    result = asyncio.run(writer.create_campaign(_config(), "idem-c1"))
    assert sent == []
    assert result.platform_response_snapshot["operation"] == "create_campaign"
    assert result.platform_response_snapshot["dry_run"] is True


def test_create_campaign_sandbox_posts_to_account_with_validate_only():
    captured: list[tuple[str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.url.path, request.content))
        return httpx.Response(200, json={"id": "23842"})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=client)
    asyncio.run(writer.create_campaign(_config(account="999"), "idem-c2"))

    assert len(captured) == 1
    path, body = captured[0]
    assert path.endswith("/act_999/campaigns")
    assert b"validate_only" in body
    assert b"PAUSED" in body  # 안전 — 생성 후 사람이 켜야 게재
    assert b"is_adset_budget_sharing_enabled" in body  # v21 필수 (실 API 검증)


def test_create_campaign_does_not_double_act_prefix():
    # ad_account_id가 이미 act_ 접두사를 가지면(.env 정본 형태) act_act_ 이중 부착 금지.
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url.path)
        return httpx.Response(200, json={"id": "23842"})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=client)
    asyncio.run(writer.create_campaign(_config(account="act_555"), "idem-c3"))

    assert captured[0].endswith("/act_555/campaigns")
    assert "act_act_" not in captured[0]


def test_create_campaign_uses_user_name_and_leads_objective():
    # 사용자가 지정한 이름과 리드 목표가 Meta 요청에 그대로 실린다 (Task1).
    captured: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.content)
        return httpx.Response(200, json={"id": "23842"})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=client)
    cfg = _config().model_copy(update={"name": "lead_test_2606", "objective": "leads"})
    asyncio.run(writer.create_campaign(cfg, "idem-c4"))

    body = captured[0]
    assert b"lead_test_2606" in body  # 사용자 이름 그대로 전송
    assert b"OUTCOME_LEADS" in body  # objective=leads → OUTCOME_LEADS 매핑


def test_create_campaign_defaults_name_and_traffic_objective():
    # 이름 미지정 → clickme-{id} 폴백, objective 기본 traffic → OUTCOME_TRAFFIC.
    captured: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.content)
        return httpx.Response(200, json={"id": "1"})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=client)
    asyncio.run(writer.create_campaign(_config(campaign="camp-x"), "idem-d"))

    body = captured[0]
    assert b"clickme-camp-x" in body  # 이름 미지정 폴백
    assert b"OUTCOME_TRAFFIC" in body  # objective 기본 = traffic


def test_create_campaign_special_ad_categories_from_config():
    # 특별 광고 카테고리(주택 등)가 캠페인 생성 요청에 실린다 (Meta 정책 신고).
    captured: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.content)
        return httpx.Response(200, json={"id": "1"})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=client)
    cfg = _config().model_copy(update={"special_ad_categories": ("HOUSING",)})
    asyncio.run(writer.create_campaign(cfg, "idem-h"))

    assert b"HOUSING" in captured[0]


def test_upload_image_returns_hash():
    # /adimages 멀티파트 업로드 → 응답에서 image_hash 추출.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"images": {"ad.jpg": {"hash": "abc123", "url": "u"}}})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=client)
    h = asyncio.run(writer.upload_image(_config(), b"fakebytes", "ad.jpg", "idem-img"))
    assert h == "abc123"


def test_create_ad_attaches_image_hash():
    # 업로드한 image_hash가 광고 소재(link_data)에 실린다.
    captured: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.content)
        return httpx.Response(200, json={"id": "1"})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=client)
    asyncio.run(
        writer.create_ad(
            _config(),
            "adset1",
            "idem-ad",
            page_id="PAGE",
            form_id="FORM",
            image_hash="IMGHASH",
        )
    )
    assert b"IMGHASH" in captured[0]


# ── executor 디스패치 ────────────────────────────────────────────


def test_executor_dispatches_create_campaign_with_config():
    cfg = _config()
    proposal = make_proposal(
        action_type="CREATE_CAMPAIGN",
        action_tier=ActionTier.TIER_3,
        target_object_ids=("111",),  # 신규 생성 — 대상은 ad_account
        evidence_metrics={"campaign_config": cfg.model_dump(mode="json")},
    )
    action = make_action(proposal)
    writer = FakeWriter()
    executor, _audit, _idem, _budget = build_executor(writer)

    result = asyncio.run(executor.execute(action, proposal))

    assert result.status is ResultStatus.SUCCESS
    assert writer.calls[0][0] == "CREATE_CAMPAIGN"
    assert writer.calls[0][1] == cfg.campaign_id  # config의 campaign_id로 호출


def test_executor_rejects_create_campaign_without_config():
    proposal = make_proposal(
        action_type="CREATE_CAMPAIGN",
        action_tier=ActionTier.TIER_3,
        target_object_ids=("111",),
        evidence_metrics={},  # config 누락
    )
    action = make_action(proposal)
    executor, _audit, _idem, _budget = build_executor(FakeWriter())

    result = asyncio.run(executor.execute(action, proposal))
    # config 없으면 어댑터 호출 전 ValueError → executor가 PLATFORM_ERROR 결과로 수렴
    assert result.status is ResultStatus.FAILED


# ── 재생성 패키징 ────────────────────────────────────────────────


class _StubGen:
    async def generate(self, _diagnosis, _count):
        return [
            CreativeCandidate(
                candidate_id="c1", copy="여름 신상 런칭", idx=0, image_ref="s3/new.png"
            )
        ]


def test_regeneration_packages_create_campaign_with_config():
    cfg = _config()
    context = RemediationContext(
        ad_account_id="111",
        target_object_ids=("111",),
        budget_before_krw=0,
        budget_after_krw=50_000,
        run_days=7,
        expected_state_version=STATE_VERSION,
        approval_policy_version=POLICY_VERSION,
        action_type="CREATE_CAMPAIGN",
        campaign_config=cfg,
    )
    diagnosis = DiagnosisResult(
        diagnosis_id="diag-1",
        tenant_id="org-1111",
        campaign_id="camp-new-1",
        anomaly_type=AnomalyType.BID_LOSS,
        source="agent",
        confidence=0.7,
        evidence_metrics={},
        metrics_as_of=NOW,
        status="confirmed",
    )
    from domain.management.agents.selection import InMemorySelectionRoundStore

    # clock을 주입하지 않아 기본(real UTC)을 사용 — SelectionRound.expires_at이 항상 미래
    # (InMemorySelectionRoundStore.claim()이 real wall-clock으로 만료를 검증하므로).
    agent = RemediationAgent(generator=_StubGen(), selection_store=InMemorySelectionRoundStore())

    async def _run():
        ranked = await agent.rank(diagnosis, context)
        return await agent.package(
            ranked.selection_token, tenant_id=diagnosis.tenant_id, selected_id="c1"
        )

    out = asyncio.run(_run())
    proposal = out.proposal

    assert proposal is not None
    assert proposal.action_type == "CREATE_CAMPAIGN"
    assert proposal.action_tier is ActionTier.TIER_3
    assert proposal.evidence_metrics["campaign_config"]["ad_account_id"] == "111"
    assert verify_proposal_hash(proposal)


@pytest.mark.parametrize("ts", [NOW, datetime(2026, 1, 1, tzinfo=UTC)])
def test_config_roundtrips_through_evidence_metrics(ts):
    """evidence_metrics JSON 왕복 후 CampaignConfig 재구성이 깨지지 않는다 (옵션 A 핵심)."""
    cfg = _config().model_copy(update={"start_at": ts})
    rebuilt = CampaignConfig(**cfg.model_dump(mode="json"))
    assert rebuilt.start_at == ts
    assert rebuilt.ad_account_id == cfg.ad_account_id
