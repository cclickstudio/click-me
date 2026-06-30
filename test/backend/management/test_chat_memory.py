# 채팅 장기기억 배선(우리 노선) — 식별자 도출·remember/recall 라운드트립 검증
"""chat.py가 (tenant, user) 네임스페이스를 도출해 memory_store에 적재·회수하는 헬퍼를 본다.

비로그인/익명은 (None, None)=데모 네임스페이스로 graceful 처리한다.
memory_store 자체(분기·격리)는 test_memory_store가 검증한다.
"""

from types import SimpleNamespace

import pytest

from api.routers.chat import _get_memory, _memory_ids
from core.schemas import ChatMessage, ChatRequest


def _body(**kw) -> ChatRequest:
    return ChatRequest(session_id="s", messages=[ChatMessage(role="user", content="hi")], **kw)


def test_memory_ids_anonymous_is_none():
    # 본문·인증유저 모두 식별자 없음 → (None, None) 데모 네임스페이스로 graceful.
    ids = _memory_ids(_body(), SimpleNamespace(id=None, organization_id=None))
    assert ids == (None, None)


def test_memory_ids_body_takes_priority():
    # 본문(JWT 도입 전 임시)이 인증유저보다 우선.
    ids = _memory_ids(
        _body(user_id="u1", organization_id="org1"),
        SimpleNamespace(id="u2", organization_id="org2"),
    )
    assert ids == ("org1", "u1")


def test_memory_ids_falls_back_to_current_user():
    ids = _memory_ids(_body(), SimpleNamespace(id="u2", organization_id="org2"))
    assert ids == ("org2", "u2")


@pytest.mark.asyncio
async def test_memory_roundtrip_via_chat_store():
    # chat.py 싱글톤 store로 적재→회수, 다른 user는 격리.
    mem = _get_memory()
    await mem.remember("t-chat", "u-chat", "k1", {"note": "질문: 예산 / 제안: PAUSE_CAMPAIGN"})
    got = await mem.recall("t-chat", "u-chat")
    assert any("PAUSE_CAMPAIGN" in g.get("note", "") for g in got)
    assert await mem.recall("t-chat", "other") == []
