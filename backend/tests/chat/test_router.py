# 챗 라우터 테스트 — hermetic import 확인 + Postgres 게이트 통합 테스트.
import os
import uuid

import pytest

pg = pytest.mark.skipif(
    not os.environ.get("CHAT_TEST_DB_URL"),
    reason="CHAT_TEST_DB_URL 미설정 — Postgres 전용 테스트 skip",
)


@pytest.fixture(scope="module")
def test_client():
    """모듈 범위 TestClient — 하나의 이벤트 루프·DB 풀을 공유해 루프 교차 오염을 방지한다."""
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as client:
        yield client


def test_router_import() -> None:
    """라우터 모듈과 앱 모듈을 import할 수 있어야 한다(의존성 누락·순환 임포트 조기 탐지)."""
    import api.main  # noqa: F401
    import api.routers.chat  # noqa: F401


@pg
def test_sessions_endpoint(test_client) -> None:
    """GET /api/chat/sessions → 200 + {"sessions": [...]}."""
    r = test_client.get("/api/chat/sessions")
    assert r.status_code == 200
    body = r.json()
    assert "sessions" in body
    assert isinstance(body["sessions"], list)


@pg
def test_session_messages_endpoint(test_client) -> None:
    """GET /api/chat/sessions/{uuid}/messages → 200 + {"session_id": ..., "messages": [...]}."""
    sid = str(uuid.uuid4())
    r = test_client.get(f"/api/chat/sessions/{sid}/messages")
    assert r.status_code == 200
    body = r.json()
    assert "session_id" in body
    assert "messages" in body
    assert isinstance(body["messages"], list)


@pg
def test_complete_invalid_session_id(test_client) -> None:
    """session_id가 UUID 형식이 아니면 400을 반환한다."""
    r = test_client.post(
        "/api/chat/complete",
        json={
            "session_id": "not-a-uuid",
            "messages": [{"role": "user", "content": "테스트"}],
        },
    )
    assert r.status_code == 400


@pg
def test_complete_streams_sse(test_client) -> None:
    """POST /api/chat/complete → 200 text/event-stream, data: ... done 포함."""
    sid = str(uuid.uuid4())
    r = test_client.post(
        "/api/chat/complete",
        json={
            "session_id": sid,
            "messages": [{"role": "user", "content": "안녕"}],
        },
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    body = r.text
    assert "data:" in body
    assert "done" in body
