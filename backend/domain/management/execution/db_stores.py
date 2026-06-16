"""🅱 실행 슬라이스 영속 어댑터 — 멱등키·감사를 NeonDB(async)에 저장.

인메모리 store/sink와 동일 Protocol을 구현해 wiring 지점에서 교체된다. 메서드당
짧은 세션(get_db 패턴)을 열고 커밋한다. core(db·models)는 공유 인프라라 import 허용.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db import AsyncSessionLocal
from core.models import AuditEventRow, IdempotencyKeyRow
from domain.management.contracts.schemas import ActionResult
from domain.management.execution.audit_log import AuditEvent, mask_sensitive

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class DbIdempotencyStore:
    """idempotency_keys 기반 — key UNIQUE + INSERT ON CONFLICT DO NOTHING (게이트 #1)."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal
    ) -> None:
        self._sf = session_factory

    async def reserve(self, key: str, approval_id: str) -> bool:
        stmt = (
            pg_insert(IdempotencyKeyRow)
            .values(key=key, approval_id=approval_id, claimed=True)
            .on_conflict_do_nothing(index_elements=["key"])
        )
        async with self._sf() as session:
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount == 1  # 1 = 선점 성공, 0 = 이미 선점됨

    async def get_result(self, key: str) -> ActionResult | None:
        async with self._sf() as session:
            row = await session.get(IdempotencyKeyRow, key)
        if row is None or row.result is None:
            return None
        return ActionResult.model_validate(row.result)

    async def save_result(self, key: str, result: ActionResult) -> None:
        async with self._sf() as session:
            row = await session.get(IdempotencyKeyRow, key)
            if row is not None:
                row.result = result.model_dump(mode="json")
                await session.commit()


class DbAuditSink:
    """audit_events 기반 insert-only 감사 로그 — 민감값 마스킹 후 저장 (게이트 #7·#8)."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal
    ) -> None:
        self._sf = session_factory

    async def append(self, event: AuditEvent) -> None:
        row = AuditEventRow(
            event_id=event.event_id,
            category=event.category,
            tenant_id=event.tenant_id,
            proposal_id=event.proposal_id or "",  # 컬럼 NOT NULL — 미상이면 빈 문자열
            approval_id=event.approval_id,
            run_id=event.run_id,
            detail=mask_sensitive(event.payload),
            at=event.occurred_at,
        )
        async with self._sf() as session:
            session.add(row)
            await session.commit()

    async def for_approval(self, approval_id: str) -> tuple[AuditEvent, ...]:
        async with self._sf() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditEventRow)
                        .where(AuditEventRow.approval_id == approval_id)
                        .order_by(AuditEventRow.at)
                    )
                )
                .scalars()
                .all()
            )
        return tuple(
            AuditEvent(
                category=row.category or "",
                tenant_id=row.tenant_id,
                proposal_id=row.proposal_id,
                approval_id=row.approval_id,
                run_id=row.run_id,
                payload=row.detail,
                event_id=row.event_id or "",
                occurred_at=row.at,
            )
            for row in rows
        )
