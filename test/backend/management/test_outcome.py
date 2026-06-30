# 🅱 RemediationOutcome — 에이전트 출력 discriminated 타입 테스트
from domain.management.agents.outcome import (
    OutcomeKind,
    OutcomeReason,
    RemediationOutcome,
)


def test_observe_outcome_has_no_proposal():
    out = RemediationOutcome(kind=OutcomeKind.OBSERVE, reason=OutcomeReason.ANOMALY_WATCH)
    assert out.proposal is None
    assert out.human_review_required is False


def test_creative_unavailable_can_flag_human_review():
    out = RemediationOutcome(
        kind=OutcomeKind.CREATIVE_UNAVAILABLE,
        reason=OutcomeReason.GENERATOR_TIMEOUT,
        human_review_required=True,
    )
    assert out.kind is OutcomeKind.CREATIVE_UNAVAILABLE
    assert out.human_review_required is True


def test_awaiting_selection_carries_token_and_candidates():
    out = RemediationOutcome(
        kind=OutcomeKind.AWAITING_SELECTION,
        selection_token="tok_1",
        candidates=[{"candidate_id": "c0", "idx": 0}],
    )
    assert out.selection_token == "tok_1"
    assert out.candidates[0]["candidate_id"] == "c0"
