# 🅱 처방 eval — action 선택 정확도 채점 검증
from domain.management.evals.regeneration_eval import (
    RegenerationRecord,
    action_selection_accuracy,
    run_action_selection_eval,
)


def rec(expected, chosen, labeled=True) -> RegenerationRecord:
    return RegenerationRecord(
        case_id="x",
        baseline_score=0.0,
        candidate_scores=(),
        guardrail_passed=True,
        expected_action=expected,
        chosen_action=chosen,
        action_labeled=labeled,
    )


def test_action_selection_accuracy_grades_only_labeled():
    records = [
        rec("REPLACE_CREATIVE", "REPLACE_CREATIVE"),  # hit
        rec("PAUSE_CAMPAIGN", "INCREASE_BUDGET"),  # miss
        rec(None, None),  # 관망 정답 (None==None)
        rec("X", "Y", labeled=False),  # 미라벨 → 채점 제외
    ]
    assert action_selection_accuracy(records) == 2 / 3


def test_action_selection_accuracy_empty_is_one():
    assert action_selection_accuracy([]) == 1.0


async def test_deterministic_core_matches_fixture_ground_truth():
    """fixture가 라벨한 기대 처방을 결정론 코어가 100% 재현한다 (회귀 가드)."""
    report = await run_action_selection_eval()
    assert report.total_cases > 0
    assert report.action_selection_accuracy == 1.0
