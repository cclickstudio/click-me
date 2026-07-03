# 알림 API 테스트 — 목록/unread_count·bulk read·resolve·org 스코프·publish
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


class FakeStore:
    def __init__(self):
        self.items = [
            {
                "id": "n1",
                "project_id": "p1",
                "project_name": "프로젝트A",
                "campaign_id": "c1",
                "kind": "management.remediation_consult",
                "payload": {"campaign_name": "여름"},
                "read_at": None,
                "resolved_at": None,
                "resolution": None,
                "followup_count": 0,
                "last_notified_at": "2026-07-03T00:00:00+00:00",
                "created_at": "2026-07-03T00:00:00+00:00",
            }
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
        r = await c.post("/api/management/notifications/n1/resolve", json={"resolution": "ignored"})
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
