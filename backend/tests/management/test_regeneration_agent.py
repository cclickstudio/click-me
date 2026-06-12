"""🅱 재생성 agent — 후보 가드(P6)·tool 복구·ActionProposal 패키징 검증."""

import pytest

from domain.management.agents.regeneration import (
    MAX_CANDIDATES,
    CreativeCandidate,
    RegenerationAgent,
    RegenerationContext,
    label_action_tier,
)
from domain.management.contracts.enums import ActionTier, AnomalyType, ProposalStatus
from domain.management.contracts.schemas import DiagnosisResult, verify_proposal_hash
from tests.management.helpers import NOW, POLICY_VERSION, STATE_VERSION

CONTEXT = RegenerationContext(
    ad_account_id="act_001",
    target_object_ids=("camp-001",),
    budget_before_krw=50_000,
    budget_after_krw=50_000,
    run_days=7,
    expected_state_version=STATE_VERSION,
    approval_policy_version=POLICY_VERSION,
)


def make_diagnosis(**overrides) -> DiagnosisResult:
    fields = {
        "diagnosis_id": "diag-001",
        "tenant_id": "org-1111",
        "campaign_id": "camp-001",
        "anomaly_type": AnomalyType.QUALITY_DEGRADED,
        "source": "agent",
        "hypothesis": "품질 저하 — 시안 피로도",
        "confidence": 0.7,
        "evidence_metrics": {"quality_ranking": "below_average_35"},
        "metrics_as_of": NOW,
        "status": "confirmed",
    }
    fields.update(overrides)
    return DiagnosisResult(**fields)


def candidate(cid: str, copy: str) -> CreativeCandidate:
    return CreativeCandidate(candidate_id=cid, ad_copy=copy)


class StubGenerator:
    def __init__(self, candidates, fail_times: int = 0):
        self.candidates = candidates
        self.fail_times = fail_times

    async def generate(self, diagnosis, count):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("generation tool down")
        return self.candidates


class StubScorer:
    def __init__(self, scores: dict[str, float], fail_ids: set[str] | None = None):
        self.scores = scores
        self.fail_ids = fail_ids or set()

    async def score(self, cand):
        if cand.candidate_id in self.fail_ids:
            raise RuntimeError("simulator down")
        return self.scores[cand.candidate_id]


def build_agent(generator, scorer, **kwargs) -> RegenerationAgent:
    return RegenerationAgent(generator=generator, scorer=scorer, clock=lambda: NOW, **kwargs)


async def test_banned_expression_is_filtered():
    generator = StubGenerator(
        [
            candidate("c1", "여름맞이 신제품 출시"),
            candidate("c2", "효과 100% 보장 다이어트"),  # 금지표현
        ]
    )
    agent = build_agent(generator, StubScorer({"c1": 0.9, "c2": 0.95}))

    proposal = await agent.propose(make_diagnosis(), CONTEXT)

    assert proposal is not None
    assert proposal.evidence_metrics["selected_candidate_id"] == "c1"


async def test_candidate_cap_is_enforced():
    generator = StubGenerator([candidate(f"c{i}", f"카피 {i}") for i in range(6)])
    scorer = StubScorer({f"c{i}": 0.8 for i in range(6)})
    agent = build_agent(generator, scorer)

    proposal = await agent.propose(make_diagnosis(), CONTEXT)

    assert len(proposal.evidence_metrics["candidates"]) <= MAX_CANDIDATES


def test_candidate_cap_cannot_be_raised_beyond_policy():
    with pytest.raises(ValueError, match="P6"):
        RegenerationAgent(
            generator=StubGenerator([]), scorer=StubScorer({}), max_candidates=MAX_CANDIDATES + 1
        )


async def test_low_score_candidates_are_dropped():
    generator = StubGenerator([candidate("c1", "카피 1"), candidate("c2", "카피 2")])
    agent = build_agent(generator, StubScorer({"c1": 0.2, "c2": 0.3}))

    proposal = await agent.propose(make_diagnosis(), CONTEXT)

    assert proposal is None  # 빈손 복귀가 무리한 제안보다 낫다


async def test_generator_failure_recovers_with_retry():
    generator = StubGenerator([candidate("c1", "카피 1")], fail_times=1)
    agent = build_agent(generator, StubScorer({"c1": 0.9}))

    proposal = await agent.propose(make_diagnosis(), CONTEXT)

    assert proposal is not None


async def test_scorer_failure_falls_back_to_surviving_candidates():
    generator = StubGenerator([candidate("c1", "카피 1"), candidate("c2", "카피 2")])
    agent = build_agent(generator, StubScorer({"c2": 0.8}, fail_ids={"c1"}))

    proposal = await agent.propose(make_diagnosis(), CONTEXT)

    assert proposal.evidence_metrics["selected_candidate_id"] == "c2"


async def test_packaged_proposal_is_valid_and_hash_verified():
    generator = StubGenerator([candidate("c1", "카피 1")])
    agent = build_agent(generator, StubScorer({"c1": 0.9}))

    proposal = await agent.propose(make_diagnosis(), CONTEXT)

    assert verify_proposal_hash(proposal)
    assert proposal.status is ProposalStatus.PENDING
    assert proposal.action_tier is ActionTier.TIER_3  # 시안 교체 = Tier 3 라벨 (P1 [안])
    assert proposal.tenant_id == "org-1111"
    assert proposal.max_total_spend_krw == 50_000 * 7  # P4 산식


def test_tier_labels_follow_p1_policy_table():
    """라벨은 P1 정책표(TIER_POLICY) 단일 소스 — approval.py 판정과 같은 표."""
    assert label_action_tier("PAUSE_CAMPAIGN") is ActionTier.TIER_1
    assert label_action_tier("DECREASE_BUDGET") is ActionTier.TIER_1  # 감액 = 자율
    assert label_action_tier("INCREASE_BUDGET") is ActionTier.TIER_3  # 증액 = 사용자 승인
    assert label_action_tier("REPLACE_CREATIVE") is ActionTier.TIER_3
    assert label_action_tier("REBALANCE_BUDGET") is ActionTier.TIER_2  # v1 비활성
    assert label_action_tier("unknown_action") is ActionTier.TIER_3  # 미등록 = 보수적
