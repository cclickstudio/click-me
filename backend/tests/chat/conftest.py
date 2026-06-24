# 챗 Postgres 게이트 픽스처 — CHAT_TEST_DB_URL(개인 NeonDB) 있을 때만. JSONB/pgvector는 SQLite 불가.
import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import core.models  # noqa: F401 — projects 등 FK 대상 테이블을 Base 메타데이터에 등록
import domain.chat.models  # noqa: F401 — chat_* 테이블 등록
from core.db import _normalize_database_url

_URL = os.environ.get("CHAT_TEST_DB_URL")
pg_only = pytest.mark.skipif(not _URL, reason="CHAT_TEST_DB_URL 미설정 — Postgres 전용 테스트 skip")


@pytest_asyncio.fixture
async def pg_session_factory():
    """개인 DB 세션 팩토리. 테스트는 생성 데이터를 자체 정리(멱등).

    statement_cache_size=0: Neon pooler(PgBouncer)에서 asyncpg prepared-statement 충돌 회피.
    """
    engine = create_async_engine(
        _normalize_database_url(_URL),
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )
    sf = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sf
    finally:
        await engine.dispose()
