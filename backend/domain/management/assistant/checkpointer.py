# 어시스턴트 그래프 영속 체크포인터 — Neon Postgres. interrupt(HITL)·멀티턴 상태를 재시작에도 보존.
"""앱 시작 시 1회 풀+테이블을 준비하고, build_checkpointer가 이 싱글턴을 쓴다.

MemorySaver는 프로세스 재시작 시 승인 대기(interrupt)·대화 맥락이 사라진다. AsyncPostgresSaver는
Neon에 체크포인트를 저장해 재시작 후에도 같은 thread_id로 이어서 재개·대화할 수 있다.
초기화 실패(연결 불가 등)면 None → MemorySaver 폴백(앱은 계속 뜬다).
"""

from __future__ import annotations

import contextlib
import logging
import sys

logger = logging.getLogger("clickme")

_saver = None  # AsyncPostgresSaver | None
_pool = None


async def init_pg_checkpointer(conn_str: str | None) -> None:
    """앱 시작 시 호출 — Neon 풀 + AsyncPostgresSaver.setup()(체크포인트 테이블 멱등 생성)."""
    global _saver, _pool
    if not conn_str or _saver is not None:
        return
    if sys.platform == "win32":
        # Windows psycopg-async는 ProactorEventLoop 비호환 → 로컬은 시도 자체를 건너뛰어
        # 5초 연결 지연을 없앤다(즉시 MemorySaver). 운영(Linux EC2)에서만 Neon 영속.
        logger.info("Windows 감지 — PG 체크포인터 건너뜀(MemorySaver). 운영(Linux)에서 영속.")
        return
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: PLC0415
        from psycopg.rows import dict_row  # noqa: PLC0415
        from psycopg_pool import AsyncConnectionPool  # noqa: PLC0415

        # SQLAlchemy는 asyncpg, langgraph 체크포인터는 psycopg 사용 → 드라이버 표기 정리.
        pg = conn_str.replace("postgresql+asyncpg", "postgresql").replace(
            "postgresql+psycopg2", "postgresql"
        )
        # Neon pooler 견고 config(태호 설계 차용):
        # - check=check_connection: 유휴로 죽은 커넥션을 getconn 시 검사·교체 →
        #   Neon 유휴 종료 후 "SSL connection has been closed unexpectedly" 방지.
        # - max_idle=120: Neon 유휴 종료 전에 선제 회수.
        # - prepare_threshold=0: PgBouncer 안전(prepared statement 비활성).
        _pool = AsyncConnectionPool(
            pg,
            min_size=1,
            max_size=5,
            open=False,
            check=AsyncConnectionPool.check_connection,
            max_idle=120.0,
            kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        )
        # Windows psycopg-async는 ProactorEventLoop 비호환 → 빨리 실패해 폴백(운영 Linux는 정상).
        await _pool.open(wait=True, timeout=5.0)
        _saver = AsyncPostgresSaver(_pool)
        await _saver.setup()  # checkpoints/checkpoint_writes/... 테이블 생성(멱등)
        logger.info("Assistant checkpointer: AsyncPostgresSaver(Neon) — 영속·재시작 복구")
    except Exception as exc:  # noqa: BLE001 — 초기화 실패는 치명 아님: 인메모리로 폴백
        logger.warning("PG checkpointer 초기화 실패 → MemorySaver 폴백: %s", exc)
        _saver = None


async def close_pg_checkpointer() -> None:
    """앱 종료 시 풀 정리."""
    global _pool, _saver
    if _pool is not None:
        with contextlib.suppress(Exception):
            await _pool.close()
    _pool, _saver = None, None


def get_pg_checkpointer():
    """초기화된 AsyncPostgresSaver(없으면 None)."""
    return _saver
