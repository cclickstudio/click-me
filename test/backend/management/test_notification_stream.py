# 알림 SSE 테스트 — connected 이벤트·publish 수신·해제 정리
#
# 참고(구현 편차): httpx.ASGITransport(0.28.1, 설치 버전)는 `await self.app(scope, receive, send)`가
# "완전히 끝난 뒤"에야 Response를 만들어 반환한다(httpx/_transports/asgi.py 확인) — 즉
# 스트리밍을 실시간으로 중계하지 않고 ASGI 앱 실행 종료를 기다린다. 이 라우트는 30초
# heartbeat로 무한히 도는 구독형 SSE라 클라이언트 연결 해제 전까지 끝나지 않으므로,
# `client.stream(...)`로 감싸면 헤더조차 받기 전에 영구 대기한다(재현 확인 완료 — 라우트
# 로직 자체는 직접 호출 시 정상). 따라서 이 파일은 두 갈래로 검증한다:
#   1) SSE 비활성(404) 케이스 — 실제 HTTP 레이어(httpx) 왕복, 스트리밍 없이 즉시 응답.
#   2) connected → publish → changed → 해제 시 unsubscribe — 라우트 코루틴을 직접 호출해
#      실제 프로덕션 로직(브로커 구독/발행/정리)을 그대로 검증(ASGI 트랜스포트 우회).
from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from domain.management.remediation import broker


@pytest.fixture
def app(monkeypatch):
    from fastapi import FastAPI

    from api.routers import management as mgmt
    from core.auth import get_current_user
    from core.config import settings
    from core.db import get_db

    async def fake_require_org_id(user, db):
        return "org-1"

    monkeypatch.setattr(mgmt, "_require_org_id", fake_require_org_id)
    monkeypatch.setattr(settings, "management_notify_sse_enabled", True, raising=False)
    broker._subscribers.clear()
    application = FastAPI()
    application.include_router(mgmt.router, prefix="/api/management")
    application.dependency_overrides[get_current_user] = lambda: object()
    application.dependency_overrides[get_db] = lambda: None
    return application


@pytest.mark.asyncio
async def test_stream_disabled_returns_404(app, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "management_notify_sse_enabled", False, raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/api/management/notifications/stream")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_stream_emits_connected_then_changed(app, monkeypatch):
    from api.routers import management as mgmt

    async def fake_require_org_id(user, db):
        return "org-1"

    monkeypatch.setattr(mgmt, "_require_org_id", fake_require_org_id)
    resp = await mgmt.notifications_stream(user=object(), db=None)
    assert resp.status_code == 200
    assert resp.media_type == "text/event-stream"

    gen = resp.body_iterator
    first = await asyncio.wait_for(gen.__anext__(), timeout=2)
    assert "connected" in first
    broker.publish("org-1")
    # changed가 나올 때까지 소진(heartbeat 등 다른 청크는 스킵)
    while True:
        chunk = await asyncio.wait_for(gen.__anext__(), timeout=2)
        if "changed" in chunk:
            break
    await gen.aclose()
    assert broker._subscribers == {}  # 연결 종료(제너레이터 close) 후 정리(finally)
