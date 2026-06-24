# 챗 라우터 요청 변환 — 멀티테넌트 id 플러밍 단위 테스트(개인DB 불필요).
import uuid

import pytest
from fastapi import HTTPException

from api.routers.chat import _build_turn_request
from core.schemas import ChatMessage, ChatRequest


def _req(**kw) -> ChatRequest:
    base = {
        "session_id": str(uuid.uuid4()),
        "messages": [ChatMessage(role="user", content="안녕")],
    }
    base.update(kw)
    return ChatRequest(**base)


def test_ids_flow_into_turn_request():
    pid, uid, oid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    req = _build_turn_request(
        _req(
            project_id=str(pid),
            user_id=str(uid),
            organization_id=str(oid),
            context_campaign_id="camp_1",
        )
    )
    assert req.project_id == pid
    assert req.user_id == uid
    assert req.organization_id == oid
    assert req.context_campaign_id == "camp_1"


def test_optional_ids_default_none():
    req = _build_turn_request(_req())
    assert req.project_id is None
    assert req.user_id is None
    assert req.organization_id is None
    assert req.context_campaign_id is None


def test_last_message_and_history_split():
    req = _build_turn_request(
        _req(
            messages=[
                ChatMessage(role="user", content="첫"),
                ChatMessage(role="assistant", content="답"),
                ChatMessage(role="user", content="둘째"),
            ]
        )
    )
    assert req.user_text == "둘째"
    assert req.history == [
        {"role": "user", "content": "첫"},
        {"role": "assistant", "content": "답"},
    ]


def test_bad_session_id_400():
    with pytest.raises(HTTPException) as ei:
        _build_turn_request(_req(session_id="not-a-uuid"))
    assert ei.value.status_code == 400


def test_bad_optional_uuid_400():
    with pytest.raises(HTTPException) as ei:
        _build_turn_request(_req(user_id="bad-uuid"))
    assert ei.value.status_code == 400
