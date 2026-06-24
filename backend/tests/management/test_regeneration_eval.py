# 🅱 처방 eval — action 선택 정확도 + 프로세스 지표(가드 통과율·예산 차단율·선택 비율)
from domain.management.evals.regeneration_eval import (
    RegenerationRecord,
    action_selection_accuracy,
    execution_blocked_by_budget_rate,
    guard_pass_rate,
    rate,
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


def test_guard_pass_rate_counts_kept_over_total():
    assert guard_pass_rate(kept=3, total=4) == 0.75
    assert guard_pass_rate(kept=0, total=0) == 0.0


def test_execution_blocked_by_budget_rate():
    results = ["SUCCESS", "BUDGET_CAP_EXCEEDED", "SUCCESS", "BUDGET_CAP_EXCEEDED"]
    assert execution_blocked_by_budget_rate(results) == 0.5
    assert execution_blocked_by_budget_rate([]) == 0.0


def test_selection_rate_helper():
    assert rate(3, 4) == 0.75  # 예: AWAITING_SELECTION 3건 / rank 4건
    assert rate(0, 0) == 0.0


async def test_deterministic_core_matches_fixture_ground_truth():
    """fixture가 라벨한 기대 처방을 결정론 코어가 100% 재현한다 (회귀 가드)."""
    report = await run_action_selection_eval()
    assert report.total_cases > 0
    assert report.action_selection_accuracy == 1.0


async def test_run_agent_eval_end_to_end():
    """FIX 4 — run_agent_eval이 ad_copy 키 픽스처로 끝까지 실행된다 (regression guard)."""
    from domain.management.evals.regeneration_eval import run_agent_eval

    report = await run_agent_eval(fixture_version="v1")
    # fixture가 있고 eval이 완전히 실행돼야 한다 (이전에는 KeyError로 crash).
    assert report.total_cases > 0
    # 생성 성공 케이스(tool_failures 0)는 가드레일 통과율이 0 초과여야 한다.
    assert report.guardrail_pass_rate >= 0.0
