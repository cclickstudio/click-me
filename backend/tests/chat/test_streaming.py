# 챗 오케스트레이터 진짜 토큰 스트림 — general/CLIO 경로 통합 테스트(개인DB 불필요).
import json
import uuid

import pytest
from langgraph.checkpoint.memory import MemorySaver

from domain.chat.contracts.agent_io import ChatTurnRequest
from domain.chat.graph.builder import ChatGraphDeps, build_chat_graph
from domain.chat.service.orchestrator import ChatOrchestratorService


class _FakeStreamingClio:
    """스트리밍 CLIO 더블 — pieces를 토큰 단위로 흘린다."""

    def __init__(self, pieces: list[str]) -> None:
        self._pieces = pieces

    async def __call__(self, user_text: str, history: list, context: str | None = None) -> str:
        return "".join(self._pieces)

    async def stream(self, user_text: str, history: list, context: str | None = None):
        for p in self._pieces:
            yield p


def _parse(frames: list[str]) -> list[dict]:
    out = []
    for f in frames:
        if f.startswith("data: "):
            out.append(json.loads(f[len("data: ") :].strip()))
    return out


def _build(clio) -> ChatOrchestratorService:
    deps = ChatGraphDeps(llm=None, repo=None, memory=None, subagents={}, clio=clio)
    graph = build_chat_graph(deps, checkpointer=MemorySaver())
    return ChatOrchestratorService(graph=graph, repo=None, settings=None)


@pytest.mark.asyncio
async def test_general_route_streams_real_tokens():
    pieces = ["오늘", "은 ", "맑고", " 좋은", " 날씨", "예요."]
    svc = _build(_FakeStreamingClio(pieces))

    req = ChatTurnRequest(session_id=uuid.uuid4(), user_text="기분 좋은 인사 해줘", history=[])
    objs = _parse([f async for f in svc.stream(req)])

    tokens = [o["token"]["text"] for o in objs if "token" in o]
    # 24자 사후 분할이 아니라 CLIO가 흘린 조각 그대로여야 한다.
    assert tokens == pieces
    assert objs[-1] == {"done": {"finish_reason": "stop"}}


@pytest.mark.asyncio
async def test_general_route_without_clio_falls_back_to_chunking():
    # clio 없음 → 결정론 폴백 답변을 서비스가 청크로 분할(스트리밍 미적용 경로 회귀).
    svc = _build(None)

    req = ChatTurnRequest(session_id=uuid.uuid4(), user_text="그냥 인사", history=[])
    objs = _parse([f async for f in svc.stream(req)])

    tokens = [o["token"]["text"] for o in objs if "token" in o]
    assert "".join(tokens) == "무엇을 도와드릴까요?"
    assert objs[-1] == {"done": {"finish_reason": "stop"}}
