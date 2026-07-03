# Task 9: SSE 스트림 엔드포인트

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §5
> **실행 규칙**: 백엔드 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 파일 첫 줄 한국어 헤더 주석 · 🅰 소유 파일 수정 금지.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.
> 선행: Task 3(broker)·Task 7(알림 라우트 블록).

---

**Files:**
- Modify: `backend/api/routers/management.py` (**Task 7 블록 최상단** — `/{id}` 라우트들보다 먼저)
- Test: `test/backend/management/test_notification_stream.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

`test/backend/management/test_notification_stream.py`:

```python
# 알림 SSE 테스트 — connected 이벤트·publish 수신·해제 정리
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
async def test_stream_emits_connected_then_changed(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        async with client.stream("GET", "/api/management/notifications/stream") as r:
            assert r.status_code == 200
            lines = r.aiter_lines()
            first = await asyncio.wait_for(anext(lines), timeout=2)
            assert "connected" in first
            broker.publish("org-1")
            # changed가 나올 때까지 소진(빈 줄 스킵)
            while True:
                line = await asyncio.wait_for(anext(lines), timeout=2)
                if "changed" in line:
                    break
    assert broker._subscribers == {}  # 연결 종료 후 정리(finally)
```

- [ ] **Step 2: 실패 확인**

```bash
cd backend && uv run pytest ../test/backend/management/test_notification_stream.py -v
```
Expected: FAIL (404 — 라우트 없음)

- [ ] **Step 3: 구현**

Task 7 블록 최상단(주석 자리)에 — **반드시 `/notifications/{notification_id}/...` 라우트들보다 위에 선언:**

```python
@router.get("/notifications/stream")
async def notifications_stream(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """알림 변경 SSE — org 브로커 구독, 이벤트는 "changed" 신호뿐(수신 측 refetch).

    선언 순서 주의: /{id} 계열보다 먼저(가로채기 방지). EventSource 대신 채팅과 같은
    fetch 스트리밍(Authorization 헤더)으로 소비한다.
    """
    if not getattr(settings, "management_notify_sse_enabled", True):
        raise HTTPException(404, "SSE 비활성 — 폴링을 사용하세요.")
    org_id = str(await _require_org_id(user, db))

    async def gen() -> AsyncIterator[str]:
        from domain.management.remediation import broker  # noqa: PLC0415

        q = broker.subscribe(org_id)
        try:
            yield 'data: {"event": "connected"}\n\n'
            while True:
                try:
                    await asyncio.wait_for(q.get(), timeout=30)
                    yield 'data: {"event": "changed"}\n\n'
                except TimeoutError:
                    yield ": keep-alive\n\n"  # 30초 heartbeat — 프록시 타임아웃 방지
        finally:
            broker.unsubscribe(org_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream")
```

`asyncio`·`AsyncIterator`·`StreamingResponse`는 management.py에 이미 임포트돼 있다.

- [ ] **Step 4: 통과 확인 + Ruff + 커밋**

```bash
cd backend && uv run pytest ../test/backend/management/test_notification_stream.py -v
cd backend && uv run ruff format . && uv run ruff check . --fix && cd ..
git add backend/api/routers/management.py test/backend/management/test_notification_stream.py
git commit -m "add: 알림 SSE 스트림 — org 구독·heartbeat·해제 정리"
```
