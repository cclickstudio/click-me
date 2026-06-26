# CLIO LangChain 스트림 — provider별 meta·token·done SSE 형태 검증(외부 호출 없이 fake llm)
import json

import pytest

import api.routers.chat as chat
from core.schemas import ChatMessage


class _FakeChunk:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self.seen = None

    async def astream(self, messages):
        self.seen = messages
        for t in self._tokens:
            yield _FakeChunk(t)


def _events(sse_chunks: list[str]) -> list[dict]:
    # "data: {...}\n\n" → dict
    return [json.loads(c[len("data: ") :].strip()) for c in sse_chunks]


def test_clio_messages_puts_system_first_and_maps_roles():
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    msgs = chat._clio_messages(
        [
            ChatMessage(role="user", content="안녕"),
            ChatMessage(role="assistant", content="네"),
        ]
    )
    assert isinstance(msgs[0], SystemMessage)
    assert isinstance(msgs[1], HumanMessage) and msgs[1].content == "안녕"
    assert isinstance(msgs[2], AIMessage) and msgs[2].content == "네"


@pytest.mark.asyncio
async def test_clio_stream_emits_meta_tokens_done(monkeypatch):
    monkeypatch.setattr(chat, "_build_clio_llm", lambda provider: _FakeLLM(["가", "나"]))
    out = [c async for c in chat._clio_stream([ChatMessage(role="user", content="질문")], "openai")]
    events = _events(out)
    assert events[0] == {"meta": {"source": "clio", "label": "CLIO", "engine": "OpenAI"}}
    assert events[1] == {"token": "가"}
    assert events[2] == {"token": "나"}
    assert events[-1] == {"done": True}


@pytest.mark.asyncio
async def test_clio_stream_engine_label_per_provider(monkeypatch):
    monkeypatch.setattr(chat, "_build_clio_llm", lambda provider: _FakeLLM([]))
    for provider, label in [("gemini", "Gemini"), ("anthropic", "Claude"), ("openai", "OpenAI")]:
        out = [
            c async for c in chat._clio_stream([ChatMessage(role="user", content="q")], provider)
        ]
        assert _events(out)[0]["meta"]["engine"] == label


@pytest.mark.asyncio
async def test_clio_stream_surfaces_error_then_done(monkeypatch):
    def _boom(provider):
        raise RuntimeError("boom")

    monkeypatch.setattr(chat, "_build_clio_llm", _boom)
    out = [c async for c in chat._clio_stream([ChatMessage(role="user", content="q")], "gemini")]
    events = _events(out)
    assert events[0]["meta"]["engine"] == "Gemini"
    assert "error" in events[1]
    assert events[-1] == {"done": True}
