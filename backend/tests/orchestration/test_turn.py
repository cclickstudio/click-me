# run_turn — StateGraph(plan→execute)가 ctx로 단일·멀티 Plan을 집행
import pytest

from api.orchestration.context import TurnContext
from api.orchestration.registry import AgentRegistry
from api.orchestration.routing import KeywordMatcher, Router
from api.orchestration.turn import build_orchestrator_graph, run_turn


class _FakeManagement:
    domain = "management"

    async def ask(self, ctx, step):
        return {"answer": f"handled:{ctx.user_input}"}


class _Gen:
    domain = "generator"

    async def ask(self, ctx, step):
        return {"ad_id": "ad-9"}


class _Sim:
    domain = "simulation"

    async def ask(self, ctx, step):
        return {"sim_for": ctx.output_of("generate")["ad_id"]}


@pytest.mark.asyncio
async def test_run_turn_executes_single_step_plan():
    route = Router([KeywordMatcher("management", frozenset({"캠페인"}))]).route("캠페인 예산")
    registry = AgentRegistry()
    registry.register(_FakeManagement())
    graph = build_orchestrator_graph(registry)

    result = await run_turn(graph, route, ctx=TurnContext(user_input="캠페인 예산"))

    assert result == {"answer": "handled:캠페인 예산"}


@pytest.mark.asyncio
async def test_run_turn_executes_multi_step_plan_threads_blackboard():
    router = Router(
        [
            KeywordMatcher("generator", frozenset({"시안"})),
            KeywordMatcher("simulation", frozenset({"시뮬"})),
        ]
    )
    route = router.route("시안 만들고 시뮬 돌려")
    registry = AgentRegistry()
    registry.register(_Gen())
    registry.register(_Sim())
    graph = build_orchestrator_graph(registry)

    result = await run_turn(graph, route, ctx=TurnContext(user_input="시안 만들고 시뮬 돌려"))

    assert result == {"sim_for": "ad-9"}


@pytest.mark.asyncio
async def test_run_turn_fails_loud_when_ctx_lacks_user_input():
    # ctx에 .user_input이 없으면 조용한 폴백 없이 AttributeError(plan_node fail-loud)
    route = Router([KeywordMatcher("management", frozenset({"캠페인"}))]).route("캠페인 예산")
    registry = AgentRegistry()
    registry.register(_FakeManagement())
    graph = build_orchestrator_graph(registry)
    with pytest.raises(AttributeError):
        await run_turn(graph, route, ctx=object())  # .user_input 없음
