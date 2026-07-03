# 알림 API 테스트 — 목록/unread_count·bulk read·resolve·org 스코프·publish·입력 파싱 방어
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

# 실물 store 계약과 일치하는 UUID 형식 id — 라우터 UUID 파싱을 통과해야 fake까지 도달한다
NID = str(uuid4())


class FakeStore:
    def __init__(self):
        self.items = [
            {
                "id": NID,
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
    assert body["notifications"][0]["id"] == NID


@pytest.mark.asyncio
async def test_bulk_read_marks_and_publishes(ctx):
    app, store, published = ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/management/notifications/read", json={"ids": [NID]})
    assert r.status_code == 200 and r.json()["updated"] == 1
    assert store.read_calls == [("org-1", [NID])]
    assert published == ["org-1"]


@pytest.mark.asyncio
async def test_resolve_marks_and_publishes(ctx):
    app, store, published = ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(
            f"/api/management/notifications/{NID}/resolve", json={"resolution": "ignored"}
        )
    assert r.status_code == 200
    assert store.resolve_calls == [("org-1", NID, "ignored")]
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
            f"/api/management/notifications/{uuid4()}/resolve", json={"resolution": "actioned"}
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_invalid_before_returns_422(ctx):
    app, _, _ = ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/management/notifications?before=not-a-date")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_invalid_before_id_returns_422(ctx):
    app, _, _ = ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(
            "/api/management/notifications?before=2026-07-03T00:00:00%2B00:00&before_id=nx"
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_non_uuid_resolve_returns_404(ctx):
    app, _, _ = ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/management/notifications/nx/resolve", json={"resolution": "ignored"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_bulk_read_ignores_non_uuid_ids(ctx):
    app, store, published = ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/management/notifications/read", json={"ids": ["not-a-uuid"]})
    assert r.status_code == 200 and r.json()["updated"] == 0
    assert store.read_calls == []  # 전부 무효 → store 호출 자체가 없음
    assert published == []  # 변화 없음 → publish 없음


@pytest.mark.asyncio
async def test_naive_before_is_coerced_to_utc(ctx):
    app, store, _ = ctx
    captured = {}

    async def capturing_list(org_id, **kw):
        captured.update(kw)
        return [], 0

    store.list_for_org = capturing_list
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/management/notifications?before=2026-07-03T00:00:00")
    assert r.status_code == 200
    assert captured["before"].tzinfo is not None  # naive → UTC 코어스
