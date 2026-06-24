# AsyncPostgresSaver 체크포인터 — HITL thread 영속(checkpoints* 테이블, 라이브러리 .setup() 소유).
"""build_async_checkpointer: psycopg 풀로 AsyncPostgresSaver 생성·setup. close 콜백 함께 반환."""

from __future__ import annotations


def to_psycopg_conninfo(url: str) -> str:
    """SQLAlchemy/asyncpg URL → psycopg3 conninfo.

    지원 포맷: `postgresql+asyncpg://`(→ postgresql://), `postgresql://`(통과).
    +asyncpg만 제거. sslmode/channel_binding은 psycopg 호환이라 유지.
    """
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


async def build_async_checkpointer(database_url: str):
    """(saver, close) 반환. saver는 setup() 완료 상태. close()로 풀 정리.

    Neon pooler 대응: prepare_threshold=None(prepared statement 비활성, PgBouncer 안전).
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    conninfo = to_psycopg_conninfo(database_url)
    pool = AsyncConnectionPool(
        conninfo=conninfo,
        max_size=5,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": None},
    )
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()  # checkpoints* 멱등 생성/마이그레이션
    except Exception:
        await pool.close()  # setup 실패 시 풀 누수 방지
        raise

    async def close() -> None:
        await pool.close()

    return saver, close
