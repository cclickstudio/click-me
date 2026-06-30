"""🅱 재생성 tool 구현체 테스트 — 템플릿 mock·미리보기 + 기본 체인 관통 (contracts·B 내부만)."""

from datetime import UTC, datetime

from management.helpers import NOW, POLICY_VERSION, STATE_VERSION

from domain.management.agents.outcome import OutcomeKind
from domain.management.agents.regeneration import (
    BANNED_EXPRESSIONS,
    MAX_CANDIDATES,
    CreativeCandidate,
    RemediationAgent,
)
from domain.management.agents.regeneration_tools import (
    MetaPreviewTool,
    TemplateCreativeGenerator,
    build_regeneration_agent,
)
from domain.management.contracts.enums import (
    ActionTier,
    AnomalyType,
    DiagnosisSource,
    DiagnosisStatus,
)
from domain.management.contracts.schemas import DiagnosisResult, verify_proposal_hash


def make_diagnosis(anomaly: AnomalyType = AnomalyType.QUALITY_DEGRADED) -> DiagnosisResult:
    return DiagnosisResult(
        diagnosis_id="dx-tools-1",
        tenant_id="org-1111",
        campaign_id="camp-001",
        anomaly_type=anomaly,
        source=DiagnosisSource.AGENT,
        hypothesis="입찰 패배 — 소재 경쟁력 저하",
        confidence=0.7,
        evidence_metrics={"cpm_surge_ratio": 1.6, "existing_ad_s3_key": "old"},
        metrics_as_of=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
        status=DiagnosisStatus.CONFIRMED,
    )


# ── 생성: 템플릿 mock ────────────────────────────────────────────────


def _copy_text(c):
    return c.copy if isinstance(c.copy, str) else " ".join(c.copy.values())


async def test_template_generator_deterministic_and_capped():
    generator = TemplateCreativeGenerator()
    first = await generator.generate(make_diagnosis(), count=2)
    second = await generator.generate(make_diagnosis(), count=2)

    assert len(first) == 2
    assert [c.copy for c in first] == [c.copy for c in second]  # 게이트 #10 재현성
    assert [c.idx for c in first] == [0, 1]  # 4-3 idx 통과 형식
    assert all(not any(banned in _copy_text(c) for banned in BANNED_EXPRESSIONS) for c in first)


async def test_template_generator_varies_by_anomaly_type():
    generator = TemplateCreativeGenerator()
    bid = await generator.generate(make_diagnosis(AnomalyType.BID_LOSS), MAX_CANDIDATES)
    quality = await generator.generate(make_diagnosis(AnomalyType.QUALITY_DEGRADED), MAX_CANDIDATES)
    fallback = await generator.generate(make_diagnosis(AnomalyType.SCHEDULE_GAP), MAX_CANDIDATES)

    assert {c.copy for c in bid} != {c.copy for c in quality}
    assert len(fallback) == MAX_CANDIDATES  # 미등록 유형은 기본 템플릿


# ── 미리보기 ─────────────────────────────────────────────────────────


async def test_preview_tool_uses_writer_readonly_method():
    tool = MetaPreviewTool()
    with_image = CreativeCandidate(candidate_id="c1", copy="x", image_ref="img_77")
    without_image = CreativeCandidate(candidate_id="c2", copy="y")

    assert "img_77" in await tool.preview(with_image)
    assert "c2" in await tool.preview(without_image)


# ── 통합: 기본 tool 체인으로 agent 끝까지 관통 ───────────────────────


async def test_default_tool_chain_reaches_proposal_via_hitl():
    from domain.management.agents.regeneration import RemediationContext

    agent = build_regeneration_agent()  # 키 없는 환경 → Template mock + Preview
    assert isinstance(agent, RemediationAgent)

    context = RemediationContext(
        ad_account_id="act_001",
        target_object_ids=("camp-001",),
        budget_before_krw=50_000,
        budget_after_krw=50_000,
        run_days=7,
        expected_state_version=STATE_VERSION,
        approval_policy_version=POLICY_VERSION,
        action_type="REPLACE_CREATIVE",
    )
    dx = make_diagnosis()
    ranked = await agent.rank(dx, context)
    assert ranked.kind is OutcomeKind.AWAITING_SELECTION
    candidates = ranked.candidates
    assert 1 <= len(candidates) <= MAX_CANDIDATES
    assert "sim_score" not in candidates[0]

    chosen = candidates[0]["candidate_id"]
    out = await agent.package(ranked.selection_token, tenant_id=dx.tenant_id, selected_id=chosen)
    assert out.kind is OutcomeKind.PROPOSED
    assert verify_proposal_hash(out.proposal)
    assert out.proposal.action_tier is ActionTier.TIER_3  # REPLACE_CREATIVE → 정책표 라벨
    assert out.proposal.evidence_metrics["selected_candidate_id"] == chosen
    assert out.proposal.metrics_as_of == dx.metrics_as_of
    assert out.proposal.expires_at > NOW
