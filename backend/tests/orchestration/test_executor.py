# Plan Executor — 단일 스텝을 Registry로 디스패치, 미등록/빈 Plan은 명시적 실패
import pytest

from api.orchestration.executor import PlanExecutionError, execute_plan
from api.orchestration.plan import PlanStep, make_plan
from api.orchestration.registry import AgentRegistry


class _FakeAgent:
    def __init__(self, domain: str, answer: str) -> None:
        self.domain = domain
        self._answer = answer
        self.seen = None

    async def ask(self, req):
        self.seen = req
        return {"answer": self._answer}


@pytest.mark.asyncio
async def test_execute_single_step_dispatches_to_registry_agent():
    agent = _FakeAgent("management", "ok")
    registry = AgentRegistry()
    registry.register(agent)
    plan = make_plan([PlanStep(domain="management", action="answer", inputs={})])

    result = await execute_plan(plan, req="REQ", registry=registry)

    assert result == {"answer": "ok"}
    assert agent.seen == "REQ"


@pytest.mark.asyncio
async def test_execute_unregistered_domain_raises():
    plan = make_plan([PlanStep(domain="generator", action="generate", inputs={})])
    with pytest.raises(PlanExecutionError):
        await execute_plan(plan, req="REQ", registry=AgentRegistry())


@pytest.mark.asyncio
async def test_execute_empty_plan_raises():
    empty = make_plan([])
    with pytest.raises(PlanExecutionError):
        await execute_plan(empty, req="REQ", registry=AgentRegistry())


@pytest.mark.asyncio
async def test_execute_multi_step_raises_in_s1():
    # S1은 단일 스텝만 — 2스텝 이상은 조용히 마지막만 처리하지 않고 명시적 실패
    registry = AgentRegistry()
    registry.register(_FakeAgent("management", "ok"))
    plan = make_plan(
        [
            PlanStep(domain="management", action="answer", inputs={}),
            PlanStep(domain="management", action="answer", inputs={"x": "y"}),
        ]
    )
    with pytest.raises(PlanExecutionError):
        await execute_plan(plan, req="REQ", registry=registry)
