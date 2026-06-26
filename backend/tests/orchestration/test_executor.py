# Plan Executor — 멀티스텝 순차 디스패치 + 블랙보드 누적, 빈/미등록 Plan은 명시적 실패
import pytest

from api.orchestration.context import TurnContext
from api.orchestration.executor import PlanExecutionError, execute_plan
from api.orchestration.plan import PlanStep, make_plan
from api.orchestration.registry import AgentRegistry


class _FakeAgent:
    def __init__(self, domain: str, payload) -> None:
        self.domain = domain
        self._payload = payload
        self.seen: list = []

    async def ask(self, ctx, step):
        self.seen.append((ctx, step))
        return self._payload


class _SimReadsGenerate:
    domain = "simulation"

    async def ask(self, ctx, step):
        upstream = ctx.output_of("generate")
        return {"sim_for": upstream["ad_id"]}


@pytest.mark.asyncio
async def test_single_step_writes_blackboard_and_returns_output():
    agent = _FakeAgent("management", {"answer": "ok"})
    registry = AgentRegistry()
    registry.register(agent)
    plan = make_plan([PlanStep(domain="management", action="answer", inputs={})])
    ctx = TurnContext(user_input="q")

    result = await execute_plan(plan, ctx, registry=registry)

    assert result == {"answer": "ok"}
    assert ctx.results["answer-1"] == {"answer": "ok"}
    assert agent.seen[0][1].id == "answer-1"  # 에이전트가 step을 받는다


@pytest.mark.asyncio
async def test_multi_step_threads_blackboard_in_order():
    gen = _FakeAgent("generator", {"ad_id": "ad-1"})
    registry = AgentRegistry()
    registry.register(gen)
    registry.register(_SimReadsGenerate())
    plan = make_plan(
        [
            PlanStep(domain="generator", action="generate", inputs={}),
            PlanStep(domain="simulation", action="simulate", inputs={}),
        ]
    )
    ctx = TurnContext(user_input="q")

    result = await execute_plan(plan, ctx, registry=registry)

    assert ctx.results["generate-1"] == {"ad_id": "ad-1"}
    assert result == {"sim_for": "ad-1"}  # 마지막 스텝 산출 반환


@pytest.mark.asyncio
async def test_unregistered_domain_raises():
    plan = make_plan([PlanStep(domain="generator", action="generate", inputs={})])
    with pytest.raises(PlanExecutionError):
        await execute_plan(plan, TurnContext(user_input="q"), registry=AgentRegistry())


@pytest.mark.asyncio
async def test_empty_plan_raises():
    empty = make_plan([])
    with pytest.raises(PlanExecutionError):
        await execute_plan(empty, TurnContext(user_input="q"), registry=AgentRegistry())


@pytest.mark.asyncio
async def test_each_step_is_traced_with_action_and_domain(monkeypatch):
    # 스텝별 트레이스 보장 — _step_trace가 스텝마다 (action, domain)으로 호출된다.
    from contextlib import nullcontext

    import api.orchestration.executor as executor

    calls: list = []

    def _fake_trace(step):
        calls.append((step.action, step.domain))
        return nullcontext()

    monkeypatch.setattr(executor, "_step_trace", _fake_trace)

    registry = AgentRegistry()
    registry.register(_FakeAgent("generator", {"ad_id": "ad-1"}))
    registry.register(_SimReadsGenerate())
    plan = make_plan(
        [
            PlanStep(domain="generator", action="generate", inputs={}),
            PlanStep(domain="simulation", action="simulate", inputs={}),
        ]
    )
    await execute_plan(plan, TurnContext(user_input="q"), registry=registry)

    assert calls == [("generate", "generator"), ("simulate", "simulation")]
