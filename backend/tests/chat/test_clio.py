# CLIO general 핸들러 — 빌더(키 없으면 None) + synthesize general 경로 통합(hermetic).
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from domain.chat.adapters.clio import build_clio
from domain.chat.contracts.agent_io import Route
from domain.chat.graph.builder import ChatGraphDeps, build_chat_graph


def test_build_clio_none_without_key():
    assert build_clio(SimpleNamespace(use_mock=True, gemini_api_key=None)) is None
    assert build_clio(SimpleNamespace(use_mock=False, gemini_api_key=None)) is None


class _FakeLLM:
    def __init__(self, tool):
        self._t = tool

    def bind_tools(self, _t):
        return self

    async def ainvoke(self, _m):
        from langchain_core.messages import AIMessage

        return AIMessage(
            content="", tool_calls=[{"name": self._t, "args": {"reason": "r"}, "id": "1"}]
        )


def _config(s="sess-clio"):
    return {"configurable": {"thread_id": s}}


@pytest.mark.asyncio
async def test_general_route_uses_clio_when_present():
    async def fake_clio(user_text, history, context=None):
        return f"CLIO 답변: {user_text}"

    deps = ChatGraphDeps(
        llm=_FakeLLM("answer_directly"),
        repo=None,
        memory=None,
        subagents={},
        executor=None,
        settings=None,
        clio=fake_clio,
    )
    g = build_chat_graph(deps, checkpointer=MemorySaver())
    out = await g.ainvoke({"messages": [HumanMessage(content="마케팅 전략 조언해줘")]}, _config())
    assert out["route"] == Route.GENERAL.value
    assert "CLIO 답변" in out["final_answer"]
    assert "마케팅 전략" in out["final_answer"]


@pytest.mark.asyncio
async def test_general_route_deterministic_without_clio():
    deps = ChatGraphDeps(
        llm=_FakeLLM("answer_directly"),
        repo=None,
        memory=None,
        subagents={},
        executor=None,
        settings=None,
        clio=None,
    )
    g = build_chat_graph(deps, checkpointer=MemorySaver())
    out = await g.ainvoke({"messages": [HumanMessage(content="안녕")]}, _config("sess-det"))
    assert out["route"] == Route.GENERAL.value
    assert out.get("final_answer")  # 결정론 폴백 답변 존재
