# 🅱 처방 agent — 자율 action 결정 + 가지별 라우팅(생성/직접/관망) 검증
from domain.management.agents.regeneration import (
    CreativeCandidate,
    RegenerationAgent,
    RegenerationContext,
    RiskAppetite,
)
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
        "evidence_metrics": {"ctr": 0.002},
        "metrics_as_of": NOW,
        "status": "confirmed",
    }
    fields.update(overrides)
    return DiagnosisResult(**fields)


def context(**overrides) -> RegenerationContext:
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
    return RegenerationContext(**fields)


class TrackingGenerator:
    def __init__(self, candidates=()):
        self.candidates = list(candidates)
        self.called = False

    async def generate(self, diagnosis, count):
        self.called = True
        return self.candidates


class StubScorer:
    def __init__(self, scores: dict[str, float]):
        self.scores = scores

    async def score(self, cand):
        return self.scores[cand.candidate_id]


def build_agent(generator, scorer):
    return RegenerationAgent(generator=generator, scorer=scorer, clock=lambda: NOW)


async def test_direct_branch_skips_generation():
    """예산/끄기 처방은 크리에이티브 생성 없이 제안을 만든다."""
    generator = TrackingGenerator()
    agent = build_agent(generator, StubScorer({}))

    proposal = await agent.propose(
        make_diagnosis(AnomalyType.BID_LOSS),
        context(risk_appetite=RiskAppetite.CONSERVATIVE),
    )

    assert proposal is not None
    assert proposal.action_type == "PAUSE_CAMPAIGN"
    assert proposal.action_tier is ActionTier.TIER_1
    assert generator.called is False
    assert verify_proposal_hash(proposal)


async def test_aggressive_bid_loss_proposes_increase_budget():
    generator = TrackingGenerator()
    agent = build_agent(generator, StubScorer({}))

    proposal = await agent.propose(
        make_diagnosis(AnomalyType.BID_LOSS),
        context(risk_appetite=RiskAppetite.AGGRESSIVE),
    )

    assert proposal.action_type == "INCREASE_BUDGET"
    assert proposal.action_tier is ActionTier.TIER_3
    assert generator.called is False


async def test_creative_branch_runs_generation():
    """품질 저하 진단은 자율로 REPLACE_CREATIVE를 골라 생성 가지를 탄다."""
    generator = TrackingGenerator([CreativeCandidate(candidate_id="c1", ad_copy="새 카피")])
    agent = build_agent(generator, StubScorer({"c1": 0.9}))

    proposal = await agent.propose(make_diagnosis(AnomalyType.QUALITY_DEGRADED), context())

    assert proposal.action_type == "REPLACE_CREATIVE"
    assert generator.called is True
    assert proposal.evidence_metrics["selected_candidate_id"] == "c1"


async def test_observe_only_returns_none():
    generator = TrackingGenerator()
    agent = build_agent(generator, StubScorer({}))

    proposal = await agent.propose(make_diagnosis(AnomalyType.LEARNING_PHASE), context())

    assert proposal is None
    assert generator.called is False


async def test_explicit_action_type_overrides_decision():
    """오케스트레이터가 명시한 action_type(예: PR2 신규 캠페인)은 자율 결정을 덮어쓴다."""
    generator = TrackingGenerator([CreativeCandidate(candidate_id="c1", ad_copy="카피")])
    agent = build_agent(generator, StubScorer({"c1": 0.9}))

    proposal = await agent.propose(
        make_diagnosis(AnomalyType.BID_LOSS),  # 자율이면 PAUSE/INCREASE
        context(action_type="REPLACE_CREATIVE"),  # 명시 override
    )

    assert proposal.action_type == "REPLACE_CREATIVE"
    assert generator.called is True
