# resolver 테스트 — AdCampaignLog 역추적(raw SQL, SQLite 검증)·org 불일치 fail-closed·실패 None
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from domain.management.remediation.resolver import resolve_project


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # resolver의 raw SQL이 쓰는 세 테이블만 최소 DDL로 생성
        await conn.execute(
            text(
                "CREATE TABLE projects (id TEXT PRIMARY KEY, organization_id TEXT, deleted_at TEXT)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE ad_generations ("
                "id TEXT PRIMARY KEY, project_id TEXT, deleted_at TEXT)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE ad_campaign_logs ("
                "id TEXT PRIMARY KEY, generation_id TEXT, campaign_id TEXT, "
                "created_at TEXT DEFAULT '2026-07-02T00:00:00')"
            )
        )
        await conn.execute(text("INSERT INTO projects VALUES ('proj-77', 'org-9', NULL)"))
        await conn.execute(text("INSERT INTO ad_generations VALUES ('gen-1', 'proj-77', NULL)"))
        # soft-delete된 generation은 역추적에서 제외돼야 한다(실 DB에 deleted_at 존재)
        await conn.execute(
            text("INSERT INTO ad_generations VALUES ('gen-del', 'proj-88', '2026-07-01')")
        )
        await conn.execute(text("INSERT INTO projects VALUES ('proj-88', 'org-9', NULL)"))
        await conn.execute(
            text(
                "INSERT INTO ad_campaign_logs (id, generation_id, campaign_id) "
                "VALUES ('log-1', 'gen-1', 'camp_meta_123')"
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_resolves_project_and_org_via_ad_campaign_log(session_factory):
    resolved = await resolve_project("camp_meta_123", session_factory=session_factory)
    assert resolved == ("proj-77", "org-9")


@pytest.mark.asyncio
async def test_fail_closed_on_org_mismatch(session_factory):
    # 기대 org와 다르면 매핑 폐기(None) — 오배정=기밀 노출이므로 fail-closed
    resolved = await resolve_project(
        "camp_meta_123", expected_org_id="org-other", session_factory=session_factory
    )
    assert resolved is None


@pytest.mark.asyncio
async def test_passes_when_expected_org_matches(session_factory):
    resolved = await resolve_project(
        "camp_meta_123", expected_org_id="org-9", session_factory=session_factory
    )
    assert resolved == ("proj-77", "org-9")


@pytest.mark.asyncio
async def test_soft_deleted_generation_is_ignored(session_factory):
    # deleted_at이 찍힌 generation만 연결된 캠페인 → 매핑 없음(None)
    async with session_factory() as db:
        from sqlalchemy import text as _text

        await db.execute(
            _text(
                "INSERT INTO ad_campaign_logs (id, generation_id, campaign_id) "
                "VALUES ('log-2', 'gen-del', 'camp_deleted_gen')"
            )
        )
        await db.commit()
    assert await resolve_project("camp_deleted_gen", session_factory=session_factory) is None


@pytest.mark.asyncio
async def test_returns_none_when_no_link(session_factory):
    assert await resolve_project("unknown_camp", session_factory=session_factory) is None


@pytest.mark.asyncio
async def test_returns_none_on_db_failure():
    def broken_factory():
        raise RuntimeError("db down")

    assert await resolve_project("camp_meta_123", session_factory=broken_factory) is None
