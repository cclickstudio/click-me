# Planner 셸 — RouteDecision을 단일 스텝 Plan으로(LLM 분해는 후속 슬라이스)
from api.orchestration.planner import build_plan
from api.orchestration.routing import KeywordMatcher, Router


def test_build_plan_makes_single_step_for_resolved_domain():
    route = Router([KeywordMatcher("management", frozenset({"캠페인"}))]).route("캠페인 예산")
    plan = build_plan(route, query="캠페인 예산")
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.domain == "management"
    assert step.action == "answer"
    assert step.inputs == {"query": "캠페인 예산"}
    assert plan.plan_hash  # 해시가 채워짐


def test_build_plan_uses_route_domain():
    route = Router([KeywordMatcher("simulation", frozenset({"시뮬"}))]).route("시뮬 돌려")
    plan = build_plan(route, query="시뮬 돌려")
    assert plan.steps[0].domain == "simulation"
