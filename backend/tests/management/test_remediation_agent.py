# 🅱 처방 agent — guard 6종 + 자율 action 결정 + 가지별 라우팅(생성/직접/관망)
from domain.management.agents.outcome import OutcomeKind, OutcomeReason
from domain.management.agents.regeneration import (
    CreativeCandidate,
    RemediationAgent,
    RemediationContext,
    RiskAppetite,
    guard_candidates,
)
from domain.management.agents.selection import InMemorySelectionRoundStore
from domain.management.contracts.enums import ActionTier, AnomalyType
from domain.management.contracts.schemas import DiagnosisResult, verify_proposal_hash
from tests.management.helpers import NOW, POLICY_VERSION, STATE_VERSION


def make_diagnosis(anomaly: AnomalyType, **overrides) -> DiagnosisResult:
    fields = {
        "diagnosis_id": "diag-001",
        "tenant_id": "org-1111",
        "campaign_id": "camp-001",
        "anomaly_type": anomaly,
        "source": "agent",
        "hypothesis": "",
        "confidence": 0.7,
        "evidence_metrics": {"ctr": 0.002, "existing_ad_s3_key": "old"},
        "metrics_as_of": NOW,
        "status": "confirmed",
    }
    fields.update(overrides)
    return DiagnosisResult(**fields)


def context(**overrides) -> RemediationContext:
    fields = {
        "ad_account_id": "act_001",
        "target_object_ids": ("camp-001",),
        "budget_before_krw": 50_000,
        "budget_after_krw": 50_000,
        "run_days": 7,
        "expected_state_version": STATE_VERSION,
        "approval_policy_version": POLICY_VERSION,
    }
    fields.update(overrides)
    return RemediationContext(**fields)


class TrackingGenerator:
    def __init__(self, candidates=()):
        self.candidates = list(candidates)
        self.called = False

    async def generate(self, diagnosis, count):
        self.called = True
        return self.candidates


def build_agent(generator):
    # clock을 주입하지 않아 기본(real UTC)을 사용 — SelectionRound.expires_at이 항상 미래
    # (InMemorySelectionRoundStore.claim()이 real wall-clock으로 만료를 검증하므로).
    return RemediationAgent(generator=generator, selection_store=InMemorySelectionRoundStore())


# ── guard 6종 ────────────────────────────────────────────────────


def _c(cid, copy="정상 카피", idx=0, image_ref="k"):
    return CreativeCandidate(candidate_id=cid, copy=copy, idx=idx, image_ref=image_ref)


def test_guard_removes_required_field_missing():
    cands = [CreativeCandidate(candidate_id="c0", copy=None, idx=0, image_ref="k")]
    kept, removed = guard_candidates(cands, existing_s3_key="old")
    assert kept == []
    assert removed[0]["reason"] == "required_field_missing"


def test_guard_removes_empty_copy():
    cands = [_c("c0", copy="   ")]
    kept, removed = guard_candidates(cands, existing_s3_key="old")
    assert kept == []
    assert removed[0]["reason"] == "empty_copy"


def test_guard_removes_banned_expression():
    cands = [_c("c0", copy="100% 보장 효과")]
    kept, removed = guard_candidates(cands, existing_s3_key="old")
    assert kept == []
    assert removed[0]["reason"] == "banned_expression"


def test_guard_removes_duplicate_candidates():
    cands = [_c("c0", copy="같은 카피"), _c("c1", copy="같은 카피")]
    kept, removed = guard_candidates(cands, existing_s3_key="old")
    assert len(kept) == 1
    assert removed[0]["reason"] == "duplicate"


def test_guard_removes_generated_new_without_s3_key():
    cands = [CreativeCandidate(candidate_id="c0", copy="카피", idx=0, image_ref=None)]
    kept, removed = guard_candidates(cands, existing_s3_key=None)
    assert kept == []
    assert removed[0]["reason"] == "asset_s3_key_missing"


def test_guard_removes_reuse_existing_without_existing_key():
    # image_ref 없음 → REUSE_EXISTING인데 기존 s3_key도 없음 → asset 누락
    cands = [CreativeCandidate(candidate_id="c0", copy="카피", idx=0, image_ref=None)]
    kept, removed = guard_candidates(cands, existing_s3_key=None)
    assert removed[0]["reason"] == "asset_s3_key_missing"


def test_guard_removes_schema_invalid_integer_copy():
    """FIX 5 — copy가 정수(non-str, non-dict) → schema_invalid."""
    cands = [CreativeCandidate(candidate_id="c0", copy=123, idx=0, image_ref="k")]  # type: ignore[arg-type]
    kept, removed = guard_candidates(cands, existing_s3_key="old")
    assert kept == []
    assert removed[0]["reason"] == "schema_invalid"


def test_guard_removes_schema_invalid_empty_dict_copy():
    """FIX 5 — copy가 headline/body/cta 없는 빈 dict → schema_invalid."""
    cands = [CreativeCandidate(candidate_id="c0", copy={}, idx=0, image_ref="k")]
    kept, removed = guard_candidates(cands, existing_s3_key="old")
    assert kept == []
    assert removed[0]["reason"] == "schema_invalid"


def test_guard_keeps_dict_copy_with_at_least_one_field():
    """FIX 5 — headline만 있어도 dict copy는 schema 유효."""
    cands = [CreativeCandidate(candidate_id="c0", copy={"headline": "제목"}, idx=0, image_ref="k")]
    kept, removed = guard_candidates(cands, existing_s3_key="old")
    assert [c.candidate_id for c in kept] == ["c0"]
    assert removed == []


def test_guard_keeps_valid_candidate():
    cands = [_c("c0")]
    kept, removed = guard_candidates(cands, existing_s3_key="old")
    assert [c.candidate_id for c in kept] == ["c0"]
    assert removed == []


def test_guard_caps_at_max_candidates():
    cands = [_c(f"c{i}", copy=f"카피 {i}") for i in range(6)]
    kept, _ = guard_candidates(cands, existing_s3_key="old")
    assert len(kept) == 3


# ── 라우팅: 직접·관망·크리에이티브 ────────────────────────────────


async def test_direct_branch_skips_generation():
    """예산/끄기 처방은 크리에이티브 생성 없이 제안을 만든다."""
    generator = TrackingGenerator()
    agent = build_agent(generator)

    out = await agent.rank(
        make_diagnosis(AnomalyType.BID_LOSS),
        context(risk_appetite=RiskAppetite.CONSERVATIVE),
    )

    assert out.kind is OutcomeKind.PROPOSED
    assert out.proposal.action_type == "PAUSE_CAMPAIGN"
    assert out.proposal.action_tier is ActionTier.TIER_1
    assert generator.called is False
    assert verify_proposal_hash(out.proposal)


async def test_aggressive_bid_loss_proposes_increase_budget():
    generator = TrackingGenerator()
    agent = build_agent(generator)

    out = await agent.rank(
        make_diagnosis(AnomalyType.BID_LOSS),
        context(risk_appetite=RiskAppetite.AGGRESSIVE),
    )

    assert out.proposal.action_type == "INCREASE_BUDGET"
    assert out.proposal.action_tier is ActionTier.TIER_3
    assert generator.called is False


async def test_creative_branch_runs_generation_awaits_selection():
    """품질 저하 진단은 자율로 REPLACE_CREATIVE를 골라 생성 가지를 탄다."""
    generator = TrackingGenerator([_c("c1", copy="새 카피")])
    agent = build_agent(generator)

    out = await agent.rank(make_diagnosis(AnomalyType.QUALITY_DEGRADED), context())

    assert out.kind is OutcomeKind.AWAITING_SELECTION
    assert generator.called is True
    assert out.candidates[0]["candidate_id"] == "c1"


async def test_observe_only_returns_observe():
    generator = TrackingGenerator()
    agent = build_agent(generator)

    out = await agent.rank(make_diagnosis(AnomalyType.LEARNING_PHASE), context())

    assert out.kind is OutcomeKind.OBSERVE
    assert out.reason is OutcomeReason.ANOMALY_WATCH
    assert generator.called is False


async def test_low_confidence_increase_observes_with_reason():
    generator = TrackingGenerator()
    agent = build_agent(generator)

    out = await agent.rank(
        make_diagnosis(AnomalyType.BID_LOSS, confidence=0.2),
        context(risk_appetite=RiskAppetite.AGGRESSIVE),
    )

    assert out.kind is OutcomeKind.OBSERVE
    assert out.reason is OutcomeReason.LOW_CONFIDENCE


async def test_explicit_action_type_overrides_decision():
    """오케스트레이터가 명시한 action_type(예: PR2 신규 캠페인)은 자율 결정을 덮어쓴다."""
    generator = TrackingGenerator([_c("c1", copy="카피")])
    agent = build_agent(generator)

    out = await agent.rank(
        make_diagnosis(AnomalyType.BID_LOSS),  # 자율이면 PAUSE/INCREASE
        context(action_type="REPLACE_CREATIVE"),  # 명시 override
    )

    assert out.kind is OutcomeKind.AWAITING_SELECTION
    assert generator.called is True


async def test_banned_candidate_filtered_then_awaits_with_survivor():
    generator = TrackingGenerator(
        [_c("c1", copy="여름맞이 신제품"), _c("c2", copy="효과 100% 보장")]
    )
    agent = build_agent(generator)

    out = await agent.rank(make_diagnosis(AnomalyType.QUALITY_DEGRADED), context())

    assert [c["candidate_id"] for c in out.candidates] == ["c1"]


async def test_packaged_proposal_is_valid_and_hash_verified():
    generator = TrackingGenerator([_c("c1", copy="카피 1")])
    agent = build_agent(generator)
    dx, ctx = make_diagnosis(AnomalyType.QUALITY_DEGRADED), context()
    ranked = await agent.rank(dx, ctx)

    out = await agent.package(ranked.selection_token, tenant_id="org-1111", selected_id="c1")

    assert verify_proposal_hash(out.proposal)
    assert out.proposal.action_tier is ActionTier.TIER_3
    assert out.proposal.tenant_id == "org-1111"
    assert out.proposal.max_total_spend_krw == 50_000 * 7
