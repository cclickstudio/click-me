# admin 계정 + RAG(kb) 데이터만 현재 Neon DB에서 새 DB로 복사하는 일회성 이전 스크립트
"""admin(role=ADMIN) 유저 + management_kb_documents(부모) + 4개 *_kb_chunks 를 새 DB로 복사한다.

새 DB는 미리 `alembic upgrade head`로 스키마가 만들어져 있어야 한다(빈 상태 가정).
- 복사 대상: users(role=ADMIN만) · management_kb_documents(부모) · 4개 *_kb_chunks(전체).
- 순서: FK 때문에 documents → chunks 순으로 넣는다(management_kb_chunks.document_id 참조).
- generated 컬럼(management_kb_chunks.search_vector)은 ORM 미매핑이라 자동 제외 → INSERT 충돌 없음.
- PK 충돌은 무시(ON CONFLICT DO NOTHING)라 재실행해도 안전(멱등).
- embedding(vector)·jsonb·tsvector 타입은 ORM 컬럼 타입이 왕복 처리한다.

기본은 DRY-RUN(소스 개수만 미리보기). 실제 복사는 --apply 필요.

실행(cd backend 후, SC 는 이 스크립트 경로):
  SC=scripts/migrate_admin_kb_to_new_db.py
  uv run python $SC --target-url "postgresql://...신규..."           # dry-run(개수만)
  uv run python $SC --target-url "postgresql://...신규..." --apply   # 실제 복사
  TARGET_DATABASE_URL="postgresql://..." uv run python $SC --apply   # env 로 타깃 지정
"""

from __future__ import annotations

# ruff: noqa: E402 — sys.path 부트스트랩 후 import (스크립트 단독 실행 지원)
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/를 모듈 경로에 추가

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.config import settings
from core.db import _normalize_database_url
from core.models import (
    ClioKbChunk,
    GeneratorKbChunk,
    ManagementKbChunk,
    ManagementKbDocument,
    SimulationKbChunk,
    User,
)

# 복사 계획 — (모델, 라벨, WHERE 필터). 리스트 순서 = 삽입 순서(FK 의존 지킴).
# documents 를 chunks 보다 먼저 둬서 management_kb_chunks.document_id FK 를 만족시킨다.
_PLAN = [
    (User, "users(ADMIN)", User.role == "ADMIN"),
    (ManagementKbDocument, "management_kb_documents", None),
    (ManagementKbChunk, "management_kb_chunks", None),
    (ClioKbChunk, "clio_kb_chunks", None),
    (SimulationKbChunk, "simulation_kb_chunks", None),
    (GeneratorKbChunk, "generator_kb_chunks", None),
]


async def _count(session, model, where) -> int:
    stmt = select(func.count()).select_from(model.__table__)
    if where is not None:
        stmt = stmt.where(where)
    return await session.scalar(stmt)


async def _copy(src_session, dst_session, model, where) -> int:
    """소스에서 읽어 타깃에 ON CONFLICT DO NOTHING 으로 삽입. 삽입 시도 행수 반환."""
    stmt = select(model.__table__)
    if where is not None:
        stmt = stmt.where(where)
    rows = [dict(m) for m in (await src_session.execute(stmt)).mappings().all()]
    if not rows:
        return 0
    pk_cols = [c.name for c in model.__table__.primary_key.columns]
    ins = pg_insert(model.__table__).values(rows).on_conflict_do_nothing(index_elements=pk_cols)
    await dst_session.execute(ins)
    return len(rows)


async def main() -> None:
    parser = argparse.ArgumentParser(description="admin + RAG 데이터를 새 DB로 복사")
    parser.add_argument(
        "--target-url",
        default=os.getenv("TARGET_DATABASE_URL"),
        help="새 DB URL(postgresql://...). 미지정 시 환경변수 TARGET_DATABASE_URL 사용.",
    )
    parser.add_argument(
        "--source-url",
        default=settings.database_url,
        help="소스 DB URL(기본: backend/.env 의 DATABASE_URL = 현재 Neon).",
    )
    parser.add_argument("--apply", action="store_true", help="실제 복사(미지정 시 dry-run).")
    args = parser.parse_args()

    src_engine = create_async_engine(_normalize_database_url(args.source_url))
    src_session_maker = async_sessionmaker(src_engine, expire_on_commit=False)

    if not args.apply:
        print("=== DRY-RUN (소스 개수만, 복사 안 함) ===")
        async with src_session_maker() as src:
            total = 0
            for model, label, where in _PLAN:
                c = await _count(src, model, where)
                total += c
                print(f"  {c:>6}  {label}")
            print(f"  ------  총 {total}행 복사 예정")
        print("실제 복사하려면 --apply 를 붙이세요.")
        await src_engine.dispose()
        return

    if not args.target_url:
        sys.exit("에러: --target-url 또는 환경변수 TARGET_DATABASE_URL 이 필요합니다.")

    dst_engine = create_async_engine(_normalize_database_url(args.target_url))
    dst_session_maker = async_sessionmaker(dst_engine, expire_on_commit=False)

    print("=== 복사 시작 ===")
    async with src_session_maker() as src, dst_session_maker() as dst:
        total = 0
        for model, label, where in _PLAN:
            n = await _copy(src, dst, model, where)
            total += n
            print(f"  +{n:>6}  {label}")
        await dst.commit()  # FK 순서대로 execute 후 한 번에 커밋
        print(f"  -------  총 {total}행 삽입 시도(기존 PK는 건너뜀)")

    await src_engine.dispose()
    await dst_engine.dispose()
    print("완료.")


if __name__ == "__main__":
    asyncio.run(main())
