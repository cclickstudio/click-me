# run_turn — 오케스트레이터 StateGraph(plan→execute)가 단일 스텝 Plan을 집행해 에이전트 결과 반환
from dataclasses import dataclass

import pytest

from api.orchestration.registry import AgentRegistry
from api.orchestration.routing import KeywordMatcher, Router
from api.orchestration.turn import build_orchestrator_graph, run_turn


@dataclass
class _Req:
    # AskRequest 대역 — run_turn은 req.question을 직접 읽는다(폴백 없음, fail-loud)
    question: str


class _FakeAgent:
    domain = "management"

    async def ask(self, req):
        return {"answer": f"handled:{req.question}"}


@pytest.mark.asyncio
async def test_run_turn_graph_executes_single_step_plan():
    route = Router([KeywordMatcher("management", frozenset({"캠페인"}))]).route("캠페인 예산")
    registry = AgentRegistry()
    registry.register(_FakeAgent())
    graph = build_orchestrator_graph(registry)

    result = await run_turn(graph, route, req=_Req(question="캠페인 예산"))

    assert result == {"answer": "handled:캠페인 예산"}


@pytest.mark.asyncio
async def test_run_turn_fails_loud_when_req_lacks_question():
    # req에 .question이 없으면 조용한 폴백 없이 AttributeError로 터진다(plan_node fail-loud)
    route = Router([KeywordMatcher("management", frozenset({"캠페인"}))]).route("캠페인 예산")
    registry = AgentRegistry()
    registry.register(_FakeAgent())
    graph = build_orchestrator_graph(registry)
    with pytest.raises(AttributeError):
        await run_turn(graph, route, req=object())  # .question 없음
