"""Meta 어댑터 계약 테스트 — 녹화 Graph API 응답으로 매핑·게이팅 검증 (네트워크 0).

httpx.MockTransport로 "URL → 녹화 JSON"을 재현한다 (generator/adapters/instagram.py 패턴).
실제 Meta 호출은 일어나지 않는다.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from domain.management.adapters.meta.client import MetaApiError, MetaClient, mask_token
from domain.management.adapters.meta.reader import MetaAdsReader
from domain.management.adapters.meta.writer import MetaAdsWriter
from domain.management.contracts.enums import CampaignState, ExecutionMode
from domain.management.contracts.schemas import CampaignConfig

_FIXTURES = Path(__file__).parents[1].parent / "domain/management/evals/fixtures/meta"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _reader_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    # /campaigns 분기는 status 체크보다 먼저 — 목록 요청 필드에도 effective_status 포함
    if path.endswith("/campaigns"):
        return httpx.Response(200, json=_load("campaigns_v21.json"))
    if path.endswith("/adsets"):
        return httpx.Response(200, json=_load("adsets_v21.json"))
    if "/insights" in path:
        if request.url.params.get("breakdowns") == "publisher_platform":
            return httpx.Response(200, json=_load("insights_platform_v21.json"))
        return httpx.Response(200, json=_load("insights_v21.json"))
    if "funding_source_details" in (request.url.params.get("fields") or ""):
        return httpx.Response(200, json=_load("account_funding_v21.json"))
    if "/delivery_estimate" in path:
        return httpx.Response(200, json=_load("delivery_estimate_v21.json"))
    if "effective_status" in (request.url.params.get("fields") or ""):
        return httpx.Response(200, json=_load("campaign_status_active_v21.json"))
    return httpx.Response(200, json={"error": {"message": "unexpected", "code": 1}})


def _reader(token: str = "EAAtest_secret_token") -> MetaAdsReader:
    client = MetaClient(token, api_version="v21.0", transport=httpx.MockTransport(_reader_handler))
    return MetaAdsReader(client=client)


def _reader_with_account(account: str = "111222333") -> MetaAdsReader:
    client = MetaClient(
        "EAAtest_secret_token",
        ad_account_id=account,
        api_version="v21.0",
        transport=httpx.MockTransport(_reader_handler),
    )
    return MetaAdsReader(client=client)


def _config() -> CampaignConfig:
    now = datetime.now(UTC)
    return CampaignConfig(
        campaign_id="23842000000000123",
        tenant_id="org_1",
        ad_account_id="111222333",
        daily_budget_krw=100_000,
        start_at=now,
        end_at=now,
    )


# ── reader 매핑 ──────────────────────────────────────────────────


def test_get_metrics_maps_insights_json():
    snap = asyncio.run(_reader().get_metrics("23842000000000123", datetime.now(UTC)))
    assert snap.impressions == 12000
    assert snap.clicks == 204
    assert snap.spend_krw == 95000
    assert snap.ctr == pytest.approx(0.017)  # Meta 백분율(1.7) → 비율 환산
    assert snap.cum_reach == 8000
    assert snap.conversions == 9
    assert snap.purchase_value_krw == 475_000
    assert snap.cvr == pytest.approx(0.05)
    assert snap.roas == pytest.approx(5.0)
    assert snap.as_of == datetime(2026, 6, 15, tzinfo=UTC)


def test_get_estimate_maps_delivery_estimate_json():
    est = asyncio.run(_reader().get_estimate(_config()))
    assert est.estimate_ready is True
    assert est.estimate_mau_lower == 1_500_000
    assert est.estimate_mau_upper == 2_000_000
    assert len(est.daily_outcomes_curve) == 2


def test_get_state_maps_effective_status():
    state = asyncio.run(_reader().get_state("23842000000000123"))
    assert state is CampaignState.ACTIVE


def test_get_platform_breakdown_splits_fb_ig():
    rows = asyncio.run(_reader().get_platform_breakdown("23842000000000123", datetime.now(UTC)))
    by = {r.platform: r for r in rows}
    assert by["facebook"].impressions == 25
    assert by["instagram"].impressions == 799
    assert by["instagram"].spend_krw == 4895
    assert by["facebook"].clicks == 2


def test_get_account_funding_detects_prepaid_exhausted():
    f = asyncio.run(_reader_with_account().get_account_funding())
    assert f.delivery_blocked is True
    assert f.block_reason == "선불 잔액 부족"
    assert f.available_balance_krw == 0


def test_list_campaigns_maps_campaign_json():
    campaigns = asyncio.run(_reader_with_account().list_campaigns())
    assert len(campaigns) == 2
    first = campaigns[0]
    assert first.campaign_id == "120250000000000001"
    assert first.name == "여름 세일"
    assert first.state is CampaignState.ACTIVE
    assert first.daily_budget_krw == 50000  # 캠페인(CBO) 예산 — KRW offset=1
    assert campaigns[1].state is CampaignState.PAUSED
    # 캠페인 노드에 예산 없음 → 광고세트 일예산 합(15000+15000)으로 보완
    assert campaigns[1].daily_budget_krw == 30000


# ── client 에러·마스킹 ───────────────────────────────────────────


def test_client_raises_meta_api_error_without_token_leak():
    token = "EAAtop_secret_value"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("error_oauth_v21.json"))

    client = MetaClient(token, transport=httpx.MockTransport(handler))
    with pytest.raises(MetaApiError) as exc:
        asyncio.run(client.get("me"))
    assert exc.value.code == 190
    assert token not in str(exc.value)  # 토큰 평문 미노출 (게이트 #8)


def test_mask_token_hides_secret():
    assert mask_token("EAAabcdef.very.secret") == "EAAa…(masked)"
    assert mask_token(None) == "<none>"
    assert mask_token("") == "<none>"


def test_client_repr_masks_token():
    assert "secret" not in repr(MetaClient("EAAsecretvalue", ad_account_id="111"))


# ── writer 모드 게이팅 ───────────────────────────────────────────


def _capturing_writer(mode: ExecutionMode, sent: list[bytes]) -> MetaAdsWriter:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.content)
        return httpx.Response(200, json={"id": "23842000000000123", "success": True})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    return MetaAdsWriter(mode=mode, client=client)


def test_dry_run_does_not_send():
    sent: list[bytes] = []
    writer = _capturing_writer(ExecutionMode.DRY_RUN, sent)
    result = asyncio.run(writer.pause("23842000000000123", "idem-1"))
    assert sent == []  # 전송 0건
    assert result.platform_response_snapshot["dry_run"] is True
    assert result.platform_response_snapshot["meta_response"] is None


def test_validate_only_sends_with_validate_only():
    sent: list[bytes] = []
    writer = _capturing_writer(ExecutionMode.VALIDATE_ONLY, sent)
    result = asyncio.run(writer.adjust_budget("23842000000000123", 120_000, "idem-2"))
    assert len(sent) == 1
    assert b"validate_only" in sent[0]  # execution_options 부착
    assert b"daily_budget" in sent[0]
    assert result.platform_response_snapshot["dry_run"] is True  # validate_only = 변경 없음


def test_live_sends_without_validate_only():
    sent: list[bytes] = []
    writer = _capturing_writer(ExecutionMode.LIVE, sent)
    result = asyncio.run(writer.pause("23842000000000123", "idem-3"))
    assert len(sent) == 1
    assert b"validate_only" not in sent[0]
    assert result.platform_response_snapshot["dry_run"] is False


def test_writer_requires_idem_key():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    with pytest.raises(ValueError, match="idem_key"):
        asyncio.run(writer.pause("23842000000000123", ""))
