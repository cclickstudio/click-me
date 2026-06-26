# Plan 구조 — plan_hash 결정론·순서민감·id 무관 + inputs 불변성 + 액션별 1-based id
from dataclasses import replace

import pytest

from api.orchestration.plan import Plan, PlanStep, compute_plan_hash, make_plan


def _steps():
    return [
        PlanStep(domain="generator", action="generate", inputs={"q": "광고"}),
        PlanStep(domain="simulation", action="simulate", inputs={}),
    ]


def test_make_plan_returns_plan_with_matching_hash():
    plan = make_plan(_steps())
    assert isinstance(plan, Plan)
    assert plan.plan_hash == compute_plan_hash(plan.steps)


def test_plan_hash_is_deterministic():
    assert compute_plan_hash(tuple(_steps())) == compute_plan_hash(tuple(_steps()))


def test_plan_hash_is_order_sensitive():
    forward = compute_plan_hash(tuple(_steps()))
    reversed_ = compute_plan_hash(tuple(reversed(_steps())))
    assert forward != reversed_


def test_make_plan_assigns_per_action_1based_ids():
    plan = make_plan(
        [
            PlanStep(domain="generator", action="generate", inputs={}),
            PlanStep(domain="simulation", action="simulate", inputs={}),
            PlanStep(domain="generator", action="generate", inputs={"v": 2}),
        ]
    )
    assert [s.id for s in plan.steps] == ["generate-1", "simulate-1", "generate-2"]


def test_plan_hash_ignores_id():
    # id가 달라도 domain/action/inputs가 같으면 plan_hash는 동일.
    step = make_plan([PlanStep(domain="generator", action="generate", inputs={})]).steps[0]
    relabeled = replace(step, id="generate-99")
    assert compute_plan_hash((step,)) == compute_plan_hash((relabeled,))


def test_plan_step_inputs_are_read_only():
    step = PlanStep(domain="management", action="answer", inputs={"query": "x"})
    with pytest.raises(TypeError):
        step.inputs["query"] = "mutated"


def test_plan_step_copies_source_dict():
    src = {"query": "x"}
    step = PlanStep(domain="management", action="answer", inputs=src)
    src["query"] = "mutated"
    assert step.inputs["query"] == "x"
