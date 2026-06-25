# 채팅 장기기억 배선 — 식별자 해석·포맷·remember/recall 롱트립 검증
"""optional_user로 도출한 (tenant, user) 네임스페이스에 기억을 적재·회수하는 채팅 헬퍼를 본다.

비로그인은 (None, None)=데모 네임스페이스로 graceful. memory_store 자체는 test_memory_store가 검증.
"""

import pytest

from api.routers.chat import _format_memory, _get_memory, _resolve_identity


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
