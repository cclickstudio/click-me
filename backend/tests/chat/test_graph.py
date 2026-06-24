# 슈퍼바이저 그래프 — 라우팅 end-to-end + interrupt/resume(hermetic, MemorySaver).
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from domain.chat.contracts.agent_io import ProposedAction, Route, SubAgentRequest, SubAgentResult
from domain.chat.graph.builder import ChatGraphDeps, build_chat_graph


class _FakeSub:
    def __init__(self, route, *, answer="결과입니다", proposed=None):
        self.route = route
        self._answer = answer
        self._proposed = proposed

    async def run(self, req: SubAgentRequest) -> SubAgentResult:
        return SubAgentResult(
            route=Route(self.route), answer=self._answer, proposed_action=self._proposed
        )


class _FakeLLM:
    def __init__(self, tool_name):
        self._t = tool_name

    def bind_tools(self, _t):
        return self

    async def ainvoke(self, _m):
        return AIMessage(
            content="", tool_calls=[{"name": self._t, "args": {"reason": "r"}, "id": "1"}]
        )


def _deps(llm=None, subs=None, executor=None):
    return ChatGraphDeps(
        llm=llm,
        repo=None,
        memory=None,
        subagents=subs or {},
        executor=executor,
        settings=None,
    )


def _config(session="sess-1"):
    return {"configurable": {"thread_id": session}}


@pytest.mark.asyncio
async def test_route_to_simulation_and_synthesize():
    subs = {"simulation": _FakeSub("simulation", answer="KPI 요약")}
    g = build_chat_graph(
        _deps(llm=_FakeLLM("route_to_simulation"), subs=subs), checkpointer=MemorySaver()
    )
    out = await g.ainvoke({"messages": [HumanMessage(content="시뮬 결과 보여줘")]}, _config())
    assert out["route"] == Route.SIMULATION.value
    assert "KPI" in out["final_answer"]


@pytest.mark.asyncio
async def test_answer_directly_skips_delegate():
    g = build_chat_graph(
        _deps(llm=_FakeLLM("answer_directly"), subs={}), checkpointer=MemorySaver()
    )
    out = await g.ainvoke({"messages": [HumanMessage(content="안녕")]}, _config())
    assert out["route"] == Route.GENERAL.value
    assert out.get("final_answer")  # synthesize ran


@pytest.mark.asyncio
async def test_keyword_fallback_no_llm():
    subs = {"management": _FakeSub("management", answer="캠페인 상태 양호")}
    g = build_chat_graph(_deps(llm=None, subs=subs), checkpointer=MemorySaver())
    out = await g.ainvoke({"messages": [HumanMessage(content="캠페인 예산 소진 어때?")]}, _config())
    assert out["route"] == Route.MANAGEMENT.value
    assert "양호" in out["final_answer"]


@pytest.mark.asyncio
async def test_interrupt_then_resume_approve_executes():
    from types import SimpleNamespace

    from domain.management.wiring import build_executor

    pa = ProposedAction(
        action_type="PAUSE_CAMPAIGN",
        target_campaign_id="camp_1",
        tier="TIER_1",
        requires_approval=True,
        rationale="지출 과다",
    )
    subs = {"management": _FakeSub("management", answer="일시중지 제안", proposed=pa)}
    executor = build_executor(SimpleNamespace(use_mock=True))
    deps = ChatGraphDeps(
        llm=_FakeLLM("route_to_management"),
        repo=None,
        memory=None,
        subagents=subs,
        executor=executor,
        settings=SimpleNamespace(use_mock=True),
    )
    g = build_chat_graph(deps, checkpointer=MemorySaver())
    cfg = _config("sess-hitl")

    first = await g.ainvoke({"messages": [HumanMessage(content="캠페인 멈춰")]}, cfg)
    assert first.get("__interrupt__")  # 승인 대기로 정지
    intr = first["__interrupt__"][0].value
    assert "approval_request" in intr

    resumed = await g.ainvoke(Command(resume={"approved": True, "approver_id": "user_1"}), cfg)
    assert resumed.get("execution_result")  # 집행됨
    assert resumed.get("final_answer")


@pytest.mark.asyncio
async def test_interrupt_then_resume_reject_skips_execute():
    pa = ProposedAction(
        action_type="PAUSE_CAMPAIGN",
        target_campaign_id="camp_1",
        tier="TIER_1",
        requires_approval=True,
        rationale="r",
    )
    subs = {"management": _FakeSub("management", answer="제안", proposed=pa)}
    deps = ChatGraphDeps(
        llm=_FakeLLM("route_to_management"),
        repo=None,
        memory=None,
        subagents=subs,
        executor=None,
        settings=None,
    )
    g = build_chat_graph(deps, checkpointer=MemorySaver())
    cfg = _config("sess-reject")
    await g.ainvoke({"messages": [HumanMessage(content="캠페인 멈춰")]}, cfg)
    resumed = await g.ainvoke(Command(resume={"approved": False}), cfg)
    assert not resumed.get("execution_result")  # 거부 → 미집행
    assert resumed.get("final_answer")


@pytest.mark.asyncio
async def test_delegate_missing_subagent_falls_through():
    # route_to_simulation 이지만 simulation 서브에이전트 미등록 → graceful, synthesize 도달
    g = build_chat_graph(
        _deps(llm=_FakeLLM("route_to_simulation"), subs={}), checkpointer=MemorySaver()
    )
    out = await g.ainvoke(
        {"messages": [HumanMessage(content="시뮬 결과 보여줘")]}, _config("sess-nosub")
    )
    assert "no subagent" in str(out.get("sub_results"))
    assert out.get("final_answer")  # synthesize는 그래도 실행
