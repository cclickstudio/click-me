# ChatOrchestratorService — SSE 프레임 순서 + HITL + resume(hermetic, 실그래프+mock 서브에이전트).
import json
import uuid

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from domain.chat.contracts.agent_io import (
    ChatTurnRequest,
    ProposedAction,
    Route,
    SubAgentRequest,
    SubAgentResult,
)
from domain.chat.graph.builder import ChatGraphDeps, build_chat_graph
from domain.chat.service.orchestrator import ChatOrchestratorService


class _FakeSub:
    def __init__(self, route, *, answer="결과", structured=None, proposed=None):
        self.route = route
        self._a, self._s, self._p = answer, structured or {}, proposed

    async def run(self, req: SubAgentRequest) -> SubAgentResult:
        return SubAgentResult(
            route=Route(self.route), answer=self._a, structured=self._s, proposed_action=self._p
        )


class _FakeLLM:
    def __init__(self, tool):
        self._t = tool

    def bind_tools(self, _t):
        return self

    async def ainvoke(self, _m):
        return AIMessage(
            content="", tool_calls=[{"name": self._t, "args": {"reason": "r"}, "id": "1"}]
        )


class _FakeRepo:
    """인메모리 ChatRepo 대역 — append/persist 호출만 기록."""

    def __init__(self):
        self.messages = []
        self.sessions = {}

    async def create_session(self, **kw):
        from datetime import UTC, datetime

        from domain.chat.contracts.schemas import SessionDTO

        sid = kw.pop("session_id", None) or uuid.uuid4()
        dto = SessionDTO(id=sid, created_at=datetime.now(UTC), updated_at=datetime.now(UTC), **kw)
        self.sessions[sid] = dto
        return dto

    async def get_session(self, sid):
        return self.sessions.get(sid)

    async def append_message(self, *, session_id, role, content, route=None, meta=None):
        from datetime import UTC, datetime

        from domain.chat.contracts.schemas import MessageDTO

        m = MessageDTO(
            id=uuid.uuid4(),
            session_id=session_id,
            role=role,
            content=content,
            route=route,
            meta=meta or {},
            created_at=datetime.now(UTC),
        )
        self.messages.append(m)
        return m

    async def get_messages(self, sid, *, limit=20):
        return []


def _parse(frames):
    """SSE 문자열 리스트 → dict 리스트."""
    out = []
    for f in frames:
        for line in f.splitlines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


def _svc(llm, subs, *, repo=None, executor=None, settings=None):
    deps = ChatGraphDeps(
        llm=llm, repo=None, memory=None, subagents=subs, executor=executor, settings=settings
    )
    graph = build_chat_graph(deps, checkpointer=MemorySaver())
    return ChatOrchestratorService(graph=graph, repo=repo or _FakeRepo(), settings=settings)


@pytest.mark.asyncio
async def test_normal_turn_frame_order():
    subs = {
        "simulation": _FakeSub(
            "simulation",
            answer="KPI 요약입니다",
            structured={"kind": "simulation_aggregate", "data": {"x": 1}},
        )
    }
    svc = _svc(_FakeLLM("route_to_simulation"), subs)
    req = ChatTurnRequest(session_id=uuid.uuid4(), user_text="시뮬 결과 보여줘")
    frames = [f async for f in svc.stream(req)]
    evs = _parse(frames)
    keys = [next(iter(e)) for e in evs]
    assert keys[0] == "meta"
    assert "tool_status" in keys
    assert "result" in keys  # structured
    assert "token" in keys
    assert keys[-1] == "done"
    done = evs[-1]["done"]
    assert done["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_hitl_emits_approval_request():
    pa = ProposedAction(
        action_type="PAUSE_CAMPAIGN",
        target_campaign_id="c1",
        tier="TIER_1",
        requires_approval=True,
        rationale="지출 과다",
    )
    subs = {"management": _FakeSub("management", answer="제안", proposed=pa)}
    svc = _svc(_FakeLLM("route_to_management"), subs)
    req = ChatTurnRequest(session_id=uuid.uuid4(), user_text="캠페인 멈춰")
    evs = _parse([f async for f in svc.stream(req)])
    keys = [next(iter(e)) for e in evs]
    assert "approval_request" in keys
    assert evs[-1]["done"]["finish_reason"] == "awaiting_approval"
    ar = next(e["approval_request"] for e in evs if "approval_request" in e)
    assert ar["action_type"] == "PAUSE_CAMPAIGN" and ar["thread_id"]


@pytest.mark.asyncio
async def test_resume_executes_and_finishes():
    from types import SimpleNamespace

    from domain.management.wiring import build_executor

    pa = ProposedAction(
        action_type="PAUSE_CAMPAIGN",
        target_campaign_id="c1",
        tier="TIER_1",
        requires_approval=True,
        rationale="r",
    )
    subs = {"management": _FakeSub("management", answer="제안", proposed=pa)}
    executor = build_executor(SimpleNamespace(use_mock=True))
    repo = _FakeRepo()
    svc = _svc(
        _FakeLLM("route_to_management"),
        subs,
        repo=repo,
        executor=executor,
        settings=SimpleNamespace(use_mock=True),
    )
    sid = uuid.uuid4()
    req = ChatTurnRequest(session_id=sid, user_text="캠페인 멈춰")
    # 1턴: interrupt까지
    evs1 = _parse([f async for f in svc.stream(req)])
    thread_id = next(e["approval_request"]["thread_id"] for e in evs1 if "approval_request" in e)
    # resume: 승인
    evs2 = _parse(
        [f async for f in svc.resume(thread_id, {"approved": True, "approver_id": "user_1"})]
    )
    keys2 = [next(iter(e)) for e in evs2]
    assert "token" in keys2
    assert evs2[-1]["done"]["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_repo_failure_does_not_break_stream():
    class _BrokenRepo(_FakeRepo):
        async def append_message(self, **kw):
            raise RuntimeError("DB down")

    subs = {"simulation": _FakeSub("simulation", answer="KPI")}
    svc = _svc(_FakeLLM("route_to_simulation"), subs, repo=_BrokenRepo())
    req = ChatTurnRequest(session_id=uuid.uuid4(), user_text="시뮬 결과")
    evs = _parse([f async for f in svc.stream(req)])
    assert evs[-1]["done"]["finish_reason"] == "stop"  # repo 실패해도 스트림 정상 완료
