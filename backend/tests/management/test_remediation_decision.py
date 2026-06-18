# 🅱 처방 결정 코어 — 진단+의향 → action 선택 매핑 검증
import pytest

from domain.management.agents.regeneration import RiskAppetite, decide_action
from domain.management.contracts.enums import AnomalyType
from domain.management.contracts.schemas import DiagnosisResult
from tests.management.helpers import NOW


def make_diagnosis(anomaly: AnomalyType, **overrides) -> DiagnosisResult:
    fields = {
        "diagnosis_id": "diag-001",
        "tenant_id": "org-1111",
        "campaign_id": "camp-001",
        "anomaly_type": anomaly,
        "source": "agent",
        "hypothesis": "",
        "confidence": 0.7,
        "evidence_metrics": {},
        "metrics_as_of": NOW,
        "status": "confirmed",
    }
    fields.update(overrides)
    return DiagnosisResult(**fields)


@pytest.mark.parametrize(
    ("anomaly", "expected"),
    [
        (AnomalyType.QUALITY_DEGRADED, "REPLACE_CREATIVE"),
        (AnomalyType.REVIEW_REJECTED, "REPLACE_CREATIVE"),
        (AnomalyType.AUDIENCE_TOO_NARROW, "CREATE_CAMPAIGN"),
    ],
)
def test_creative_anomalies_map_to_creative_actions(anomaly, expected):
    assert decide_action(make_diagnosis(anomaly), RiskAppetite.CONSERVATIVE) == expected


def test_bid_loss_aggressive_increases_budget():
    decision = decide_action(make_diagnosis(AnomalyType.BID_LOSS), RiskAppetite.AGGRESSIVE)
    assert decision == "INCREASE_BUDGET"


def test_bid_loss_conservative_pauses():
    decision = decide_action(make_diagnosis(AnomalyType.BID_LOSS), RiskAppetite.CONSERVATIVE)
    assert decision == "PAUSE_CAMPAIGN"


def test_budget_exhausted_follows_risk_appetite():
    diag = make_diagnosis(AnomalyType.BUDGET_EXHAUSTED)
    assert decide_action(diag, RiskAppetite.AGGRESSIVE) == "INCREASE_BUDGET"
    assert decide_action(diag, RiskAppetite.CONSERVATIVE) == "PAUSE_CAMPAIGN"


@pytest.mark.parametrize(
    "anomaly",
    [
        AnomalyType.LEARNING_PHASE,
        AnomalyType.REVIEW_DELAY,
        AnomalyType.INCONCLUSIVE,
        AnomalyType.SCHEDULE_GAP,  # RESCHEDULE 액션 부재 → 관망
    ],
)
def test_observe_only_anomalies_return_none(anomaly):
    assert decide_action(make_diagnosis(anomaly), RiskAppetite.AGGRESSIVE) is None
