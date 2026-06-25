# 채팅 장기기억 배선 — 식별자 해석·포맷·remember/recall 롱트립 검증
"""optional_user로 도출한 (tenant, user) 네임스페이스에 기억을 적재·회수하는 채팅 헬퍼를 본다.

비로그인은 (None, None)=데모 네임스페이스로 graceful. memory_store 자체는 test_memory_store가 검증.
"""

import pytest

from api.assistant.contracts import Intent, SubagentRequest
from api.assistant.intent import classify_intent
from api.routers.chat import _format_memory, _get_memory, _resolve_identity
from core.schemas import ChatMessage


def _req(text: str) -> SubagentRequest:
    return SubagentRequest(messages=[ChatMessage(role="user", content=text)], session_id="t")


@pytest.mark.asyncio
async def test_keyword_fallback_routes_benchmark_to_manage():
    """LLM 분류가 주 경로지만, 키 없을 때 키워드 폴백도 벤치마크·플랫폼을 MANAGE로 잡는다."""
    for q in [
        "메타는 cpm이 어때?",
        "틱톡은 cpm이 어때?",
        "CPM 벤치마크 알려줘",
        "입찰 전략 바꿔줘",
    ]:
        assert await classify_intent(_req(q), [Intent.MANAGE], llm=None) == Intent.MANAGE
    # 일반 질문은 ADVISE(→ Gemini CLIO)
    assert (
        await classify_intent(_req("오늘 날씨 어때?"), [Intent.MANAGE], llm=None) == Intent.ADVISE
    )


def test_format_memory_empty_returns_none():
    assert _format_memory([]) is None
    assert _format_memory([{"x": 1}]) is None  # note 키 없음


def test_format_memory_joins_notes():
    out = _format_memory([{"note": "A"}, {"note": "B"}])
    assert out is not None
    assert "A" in out and "B" in out
    assert out.startswith("[이전 대화")


@pytest.mark.asyncio
async def test_resolve_identity_anonymous_is_none():
    # 비로그인(user=None)이면 db를 건드리지 않고 (None, None).
    assert await _resolve_identity(None, None) == (None, None)


@pytest.mark.asyncio
async def test_memory_roundtrip_via_chat_store():
    mem = _get_memory()
    await mem.remember("t-chat", "u-chat", "k1", {"note": "질문: 예산 / 제안: PAUSE_CAMPAIGN"})
    got = await mem.recall("t-chat", "u-chat")
    assert any("PAUSE_CAMPAIGN" in g["note"] for g in got)
    # 다른 user는 격리
    assert await mem.recall("t-chat", "other") == []
