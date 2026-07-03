# ask_general_knowledge tool 골든 — fake retriever 주입으로 인용·게이트·폴백 검증(DB 미접근)
"""test_tools.py와 동일하게 @tool 래퍼의 .coroutine으로 직접 호출한다."""

import pytest

from api.assistant.subagent_tools import build_chat_tools
from api.routers.chat import _assemble_chat_meta
from core.config import settings

_HITS = [
    {
        "source": "marketing_terms.md",
        "title": "CPM",
        "chunk": "CPM 정의...",
        "score": 0.8,
        "cosine_score": 0.8,
    },
    {
        "source": "advertising_general_knowledge.md",
        "title": "어트리뷰션",
        "chunk": "어트리뷰션...",
        "score": 0.6,
        "cosine_score": 0.6,
    },
]


class _FakeRetriever:
    def __init__(self, hits):
        self._hits = hits

    async def search(self, query, k=4):
        return self._hits


def _tools(hits):
    built = build_chat_tools(settings, clio_retriever=_FakeRetriever(hits))
    return {t.name: t for t in built}


def _state(**kw):
    base = {
        "project_id": None,
        "session_id": "t",
        "user_id": None,
        "org_id": None,
        "messages": [],
    }
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_no_retriever_returns_notice_without_meta():
    # USE_MOCK=true(루트 conftest) → 내부 생성 안 됨 → retriever None 폴백.
    tools = {t.name: t for t in build_chat_tools(settings)}
    cmd = await tools["ask_general_knowledge"].coroutine(
        query="CPM이 뭐야", state=_state(), tool_call_id="t1"
    )
    assert "sub_meta" not in cmd.update
    assert "지식베이스" in cmd.update["messages"][0].content


@pytest.mark.asyncio
async def test_hits_emit_clio_citations():
    tools = _tools(_HITS)
    cmd = await tools["ask_general_knowledge"].coroutine(
        query="CPM이 뭐야", state=_state(), tool_call_id="t1"
    )
    clio_meta = cmd.update["sub_meta"]["clio"]
    assert clio_meta["source"] == "clio"
    assert clio_meta["citations"][0] == {
        "kind": "kb",
        "source": "marketing_terms.md",
        "title": "CPM",
    }
    assert "[1] CPM" in cmd.update["messages"][0].content


@pytest.mark.asyncio
async def test_low_cosine_gated_out():
    weak = [dict(_HITS[0], cosine_score=0.1, score=0.1)]
    tools = _tools(weak)
    cmd = await tools["ask_general_knowledge"].coroutine(
        query="무관한 질문", state=_state(), tool_call_id="t1"
    )
    assert "sub_meta" not in cmd.update
    assert "근거가 없어" in cmd.update["messages"][0].content


def test_assemble_chat_meta_collects_clio():
    state = {
        "sub_meta": {
            "clio": {
                "source": "clio",
                "label": "광고 지식 베이스",
                "citations": [{"kind": "kb", "source": "s", "title": "t"}],
            }
        }
    }
    meta = _assemble_chat_meta(state, "engine-x")
    assert meta["citations"] == [{"kind": "kb", "source": "s", "title": "t"}]
    assert meta["source"] == "clio"
    assert meta["label"] == "광고 지식 베이스"
