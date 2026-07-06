# Task 7: 알림 API — 목록·bulk read·resolve (+SSE publish)

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §2
> **실행 규칙**: 백엔드 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 파일 첫 줄 한국어 헤더 주석 · 🅰 소유 파일 수정 금지.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Modify: `backend/api/routers/management.py` (notify-scan 엔드포인트 아래에 추가)
- Test: `test/backend/management/test_notification_api.py` (신규)

**패턴:** test_notify_scan_endpoint.py처럼 FastAPI 앱 조립 + `_require_org_id` monkeypatch + store를 라우터 모듈 레벨 팩토리(`_notification_store`)로 두고 테스트에서 교체.

- [ ] **Step 1: 실패 테스트 작성**

`test/backend/management/test_notification_api.py`:

```python
# 알림 API 테스트 — 목록/unread_count·bulk read·resolve·org 스코프·publish
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


class FakeStore:
    def __init__(self):
        self.items = [
            {"id": "n1", "project_id": "p1", "project_name": "프로젝트A", "campaign_id": "c1",
             "kind": "management.remediation_consult", "payload": {"campaign_name": "여름"},
             "read_at": None, "resolved_at": None, "resolution": None, "followup_count": 0,
             "last_notified_at": "2026-07-03T00:00:00+00:00",
             "created_at": "2026-07-03T00:00:00+00:00"}
        ]
        self.read_calls, self.resolve_calls = [], []

    async def list_for_org(self, org_id, **kw):
        return self.items, 1

    async def mark_read(self, org_id, ids, now):
        self.read_calls.append((org_id, ids))
        return len(ids)

    async def resolve(self, org_id, notification_id, resolution, now):
        self.resolve_calls.append((org_id, notification_id, resolution))
        return True


@pytest.fixture
def ctx(monkeypatch):
    from fastapi import FastAPI

    from api.routers import management as mgmt
    from core.auth import get_current_user
    from core.db import get_db

    store = FakeStore()
    published = []
    monkeypatch.setattr(mgmt, "_notification_store", lambda: store)
    monkeypatch.setattr(mgmt, "_publish_org", published.append)

    async def fake_require_org_id(user, db):
        return "org-1"

    monkeypatch.setattr(mgmt, "_require_org_id", fake_require_org_id)
    application = FastAPI()
    application.include_router(mgmt.router, prefix="/api/management")
    application.dependency_overrides[get_current_user] = lambda: object()
    application.dependency_overrides[get_db] = lambda: None
    return application, store, published


@pytest.mark.asyncio
async def test_list_returns_items_and_org_wide_unread(ctx):
    app, store, _ = ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/management/notifications")
    assert r.status_code == 200
    body = r.json()
    assert body["unread_count"] == 1
    assert body["notifications"][0]["id"] == "n1"


@pytest.mark.asyncio
async def test_bulk_read_marks_and_publishes(ctx):
    app, store, published = ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/management/notifications/read", json={"ids": ["n1"]})
    assert r.status_code == 200 and r.json()["updated"] == 1
    assert store.read_calls == [("org-1", ["n1"])]
    assert published == ["org-1"]


@pytest.mark.asyncio
async def test_resolve_marks_and_publishes(ctx):
    app, store, published = ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(
            "/api/management/notifications/n1/resolve", json={"resolution": "ignored"}
        )
    assert r.status_code == 200
    assert store.resolve_calls == [("org-1", "n1", "ignored")]
    assert published == ["org-1"]


@pytest.mark.asyncio
async def test_list_rejects_invalid_limit(ctx):
    app, _, _ = ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/management/notifications?limit=0")
    assert r.status_code == 422  # Query(ge=1, le=200) 검증


@pytest.mark.asyncio
async def test_resolve_unknown_returns_404(ctx):
    app, store, _ = ctx

    async def not_found(org_id, notification_id, resolution, now):
        return False

    store.resolve = not_found
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(
            "/api/management/notifications/nx/resolve", json={"resolution": "actioned"}
        )
    assert r.status_code == 404
```

- [ ] **Step 2: 실패 확인**

```bash
cd backend && uv run pytest ../test/backend/management/test_notification_api.py -v
```
Expected: FAIL (라우트·`_notification_store` 없음)

- [ ] **Step 3: 라우터 구현**

`backend/api/routers/management.py`의 notify-scan 엔드포인트(`return {"scanned_findings": ...}` 뒤) 아래에 추가. **주의: SSE stream 라우트(Task 9)를 이 블록 최상단(다른 `/notifications/{...}`보다 먼저)에 둘 자리를 주석으로 남긴다.**

```python
# ── 운영 알림(이상 감지 C안) — 스펙 docs/superpowers/specs/2026-07-03-…-design.md §2 ──
# (Task 9의 GET /notifications/stream은 반드시 이 블록의 /{id} 라우트들보다 먼저 선언)


def _notification_store():
    """알림 store 팩토리 — 테스트에서 monkeypatch로 교체하는 seam."""
    from domain.management.remediation.notification_store import (  # noqa: PLC0415
        DbNotificationStore,
    )

    return DbNotificationStore()


def _publish_org(org_id: str) -> None:
    from domain.management.remediation import broker  # noqa: PLC0415

    broker.publish(org_id)


class NotificationReadRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)


class NotificationResolveRequest(BaseModel):
    resolution: Literal["ignored", "actioned"]


@router.get("/notifications")
async def list_notifications(
    project_id: str | None = None,
    unread_only: bool = False,
    include_resolved: bool = False,
    limit: int = Query(50, ge=1, le=200),
    before: str | None = None,
    before_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """org 전체 알림 목록 + 배지용 unread_count(필터 무관 org 전체 미해결·미열람 수).

    커서는 (before, before_id) 복합 — 마지막 행의 last_notified_at·id를 그대로 넘긴다.
    """
    org_id = str(await _require_org_id(user, db))
    before_dt = datetime.fromisoformat(before) if before else None
    items, unread = await _notification_store().list_for_org(
        org_id,
        project_id=project_id,
        unread_only=unread_only,
        include_resolved=include_resolved,
        limit=limit,
        before=before_dt,
        before_id=before_id,
    )
    return {"notifications": items, "unread_count": unread}


@router.post("/notifications/read")
async def read_notifications(
    body: NotificationReadRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """bulk 열람 마킹 — 패널이 화면에 보인 카드를 일괄 read 처리(단건도 같은 경로)."""
    org_id = str(await _require_org_id(user, db))
    updated = await _notification_store().mark_read(org_id, body.ids, datetime.now(UTC))
    if updated:
        _publish_org(org_id)  # 다른 탭 배지 동기화
    return {"updated": updated}


@router.post("/notifications/{notification_id}/resolve")
async def resolve_notification(
    notification_id: str,
    body: NotificationResolveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """무시/조치됨 마킹 — ignored는 같은 (캠페인,이상) 재통지 완전 억제(스펙 §0)."""
    org_id = str(await _require_org_id(user, db))
    ok = await _notification_store().resolve(
        org_id, notification_id, body.resolution, datetime.now(UTC)
    )
    if not ok:
        raise HTTPException(404, "알림을 찾을 수 없습니다.")  # 타 org 포함 fail-closed
    _publish_org(org_id)
    return {"resolved": True, "resolution": body.resolution}
```

`BaseModel`·`Field`·`Literal`·`datetime`·`UTC`는 management.py에 이미 임포트돼 있다(파일 상단 확인). `Query`는 없으므로 23행 fastapi 임포트에 추가: `from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile`.

- [ ] **Step 4: 통과 확인 + Ruff + 커밋**

```bash
cd backend && uv run pytest ../test/backend/management/test_notification_api.py -v
cd backend && uv run ruff format . && uv run ruff check . --fix && cd ..
git add backend/api/routers/management.py test/backend/management/test_notification_api.py
git commit -m "add: 알림 API — 목록(unread_count)·bulk read·resolve + SSE publish"
```
