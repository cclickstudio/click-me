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


# ---- 정책화(PR2): 역량 카탈로그·신원 맥락 주입 ----
@pytest.mark.asyncio
async def test_decide_route_injects_capability_and_identity():
    # 레지스트리 역량 + 신원 스코프/엔티티가 라우팅 시스템 프롬프트에 주입되는지(값 노출 아님).
    captured = {}

    class _CapLLM:
        def bind_tools(self, _t):
            return self

        async def ainvoke(self, msgs):
            captured["sys"] = msgs[0].content
            return AIMessage(
                content="",
                tool_calls=[{"name": "route_to_generation", "args": {"reason": "r"}, "id": "1"}],
            )

    from domain.chat.contracts.capabilities import CAPABILITIES

    route = await decide_route(
        [HumanMessage(content="내가 생성한 광고 몇개")],
        llm=_CapLLM(),
        capabilities=CAPABILITIES,
        identity={"organization_id": "o1", "simulation_id": "s1"},
    )
    assert route is Route.GENERATION
    assert "역량 카탈로그" in captured["sys"] and "광고 생성" in captured["sys"]
    assert "신원 스코프" in captured["sys"] and "현재 맥락 엔티티" in captured["sys"]
