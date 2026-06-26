# Plan 구조 — plan_hash 결정론·스텝 순서 민감성 + inputs 불변성 검증
import pytest

from api.orchestration.plan import Plan, PlanStep, compute_plan_hash, make_plan


def _steps():
    return [
        PlanStep(domain="generator", action="generate", inputs={"q": "광고"}),
        PlanStep(domain="simulation", action="simulate", inputs={}),
    ]


def test_make_plan_sets_matching_hash():
    plan = make_plan(_steps())
    assert isinstance(plan, Plan)
    assert plan.steps == tuple(_steps())
    assert plan.plan_hash == compute_plan_hash(tuple(_steps()))


def test_plan_hash_is_deterministic():
    assert compute_plan_hash(tuple(_steps())) == compute_plan_hash(tuple(_steps()))


def test_plan_hash_is_order_sensitive():
    forward = compute_plan_hash(tuple(_steps()))
    reversed_ = compute_plan_hash(tuple(reversed(_steps())))
    assert forward != reversed_


def test_plan_step_inputs_are_read_only():
    # 불변성 — 확정 후 inputs 변경 시도는 거부(plan_hash 무결성 보장)
    step = PlanStep(domain="management", action="answer", inputs={"query": "x"})
    with pytest.raises(TypeError):
        step.inputs["query"] = "mutated"


def test_plan_step_copies_source_dict():
    # 외부 dict를 나중에 바꿔도 step.inputs는 영향 없음(사본화)
    src = {"query": "x"}
    step = PlanStep(domain="management", action="answer", inputs=src)
    src["query"] = "mutated"
    assert step.inputs["query"] == "x"
