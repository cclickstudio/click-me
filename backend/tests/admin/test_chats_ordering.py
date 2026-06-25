# GET /api/admin/chats가 생성일이 아니라 최근활동(updated_at) 내림차순인지 검증하는 통합 테스트.
#
# 모델이 Postgres 전용 타입(UUID/JSONB/ENUM)이라 SQLite 대체가 불가 → 실 DB(ep-soft-band)에
# 두 세션을 created_at/updated_at 다르게 심고 엔드포인트 응답에서 상대 순서를 단언한다.
# 인증은 ordering 검증과 무관하므로 require_admin 의존성만 더미 ADMIN으로 오버라이드한다.

from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy import delete

from api.routers import admin
from core.auth import require_admin
from core.db import AsyncSessionLocal, get_db
from core.models import ChatSession, User


@pytest_asyncio.fixture
async def seeded_sessions():
    """두 채팅 세션을 심는다.

    - A: 오래 전 생성(created_at = now-1h) + 방금 활동(updated_at = now)        → 위에 와야 함
    - B: 방금 생성(created_at = now) + 5분 전 활동(updated_at = now-5m)          → A 아래

    created_at 정렬이면 B가 위, updated_at 정렬이면 A가 위 → 둘을 구분.
    """
    now = datetime.utcnow()
    a_id = uuid4()
    b_id = uuid4()
    async with AsyncSessionLocal() as db:
        db.add(
            ChatSession(
                id=a_id,
                project_id=None,
                title="[test] A 최근활동",
                created_at=now - timedelta(hours=1),
                updated_at=now,
            )
        )
        db.add(
            ChatSession(
                id=b_id,
                project_id=None,
                title="[test] B 방금생성",
                created_at=now,
                updated_at=now - timedelta(minutes=5),
            )
        )
        await db.commit()
    try:
        yield str(a_id), str(b_id)
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ChatSession).where(ChatSession.id.in_([a_id, b_id])))
            await db.commit()


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(admin.router, prefix="/api/admin")
    # ordering 검증이 목적 — 인증은 더미 ADMIN으로 우회, get_db는 실 DB 사용.
    application.dependency_overrides[require_admin] = lambda: User(
        id=uuid4(), login_id="test-admin", name="t", role="ADMIN", status="ACTIVE"
    )
    application.dependency_overrides[get_db] = get_db
    return application


@pytest.mark.asyncio
async def test_chats_ordered_by_updated_at_desc(app, seeded_sessions):
    a_id, b_id = seeded_sessions
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/admin/chats", params={"limit": 50})
    assert resp.status_code == 200, resp.text
    ids = [row["id"] for row in resp.json()]
    assert a_id in ids, "심은 A 세션이 목록에 없음"
    assert b_id in ids, "심은 B 세션이 목록에 없음"
    # 최근활동(updated_at) 순이면 A가 B보다 위 — created_at 순이면 반대라 실패.
    assert ids.index(a_id) < ids.index(b_id), (
        "최근활동(updated_at) 내림차순이 아님 — A(방금활동)가 B(방금생성)보다 아래에 있음"
    )
