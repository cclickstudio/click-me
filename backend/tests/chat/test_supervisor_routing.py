# 슈퍼바이저 라우팅 — LLM tool-calling 경로 + 키워드 폴백(hermetic).
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from domain.chat.contracts.agent_io import Route
from domain.chat.graph.supervisor import decide_route, keyword_route


# ---- 키워드 폴백 (llm=None) ----
@pytest.mark.parametrize(
    "text,expected",
    [
        ("캠페인 예산 소진이 어때?", Route.MANAGEMENT),
        ("이 광고 시뮬 돌려서 구매의도 봐줘", Route.SIMULATION),
        ("새 시안 카피 만들어줘", Route.GENERATION),
        ("안녕 오늘 날씨 좋다", Route.GENERAL),
    ],
)
def test_keyword_route_buckets(text, expected):
    assert keyword_route(text) is expected


@pytest.mark.asyncio
async def test_decide_route_fallback_uses_keywords():
    # llm=None → 키워드 라우팅
    route = await decide_route([HumanMessage(content="캠페인 성과 알려줘")], llm=None)
    assert route is Route.MANAGEMENT


# ---- LLM tool-calling 경로 ----
class _FakeLLM:
    def __init__(self, tool_name):
        self._tool_name = tool_name

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _msgs):
        return AIMessage(
            content="", tool_calls=[{"name": self._tool_name, "args": {"reason": "r"}, "id": "1"}]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,expected",
    [
        ("route_to_simulation", Route.SIMULATION),
        ("route_to_generation", Route.GENERATION),
        ("route_to_management", Route.MANAGEMENT),
        ("answer_directly", Route.GENERAL),
    ],
)
async def test_decide_route_llm_toolcall(tool_name, expected):
    route = await decide_route([HumanMessage(content="x")], llm=_FakeLLM(tool_name))
    assert route is expected


@pytest.mark.asyncio
async def test_decide_route_llm_no_toolcall_defaults_general():
    class _NoTool:
        def bind_tools(self, _t):
            return self

        async def ainvoke(self, _m):
            return AIMessage(content="직접 답")

    route = await decide_route([HumanMessage(content="x")], llm=_NoTool())
    assert route is Route.GENERAL
