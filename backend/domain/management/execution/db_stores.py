"""🅱 실행 슬라이스 영속 어댑터 — 멱등키·감사를 NeonDB(async)에 저장.

인메모리 store/sink와 동일 Protocol을 구현해 wiring 지점에서 교체된다. 메서드당
짧은 세션(get_db 패턴)을 열고 커밋한다. core(db·models)는 공유 인프라라 import 허용.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db import AsyncSessionLocal
from core.models import AuditEventRow, IdempotencyKeyRow, RegenerationJobRow
from domain.management.contracts.schemas import ActionResult
from domain.management.execution.audit_log import AuditEvent, mask_sensitive
from domain.management.execution.regeneration_jobs import JobStatus, RegenerationJobRecord

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

    async def release(self, key: str) -> None:
        # 결과 없이 선점만 한 행을 삭제 — 일시 실패 후 동일 키 재선점(재시도)을 허용.
        async with self._sf() as session:
            row = await session.get(IdempotencyKeyRow, key)
            if row is not None and row.result is None:
                await session.delete(row)
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

    async def for_tenant(self, tenant_id: str) -> tuple[AuditEvent, ...]:
        async with self._sf() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditEventRow)
                        .where(AuditEventRow.tenant_id == tenant_id)
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


def _row_to_record(row: RegenerationJobRow) -> RegenerationJobRecord:
    return RegenerationJobRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        campaign_id=row.campaign_id,
        status=JobStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        selection_token=row.selection_token,
        candidates=list(row.candidates or []),
        selected_candidate_id=row.selected_candidate_id,
        proposal=row.proposal,
        outcome_reason=row.outcome_reason,
        error=row.error,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


class DbRegenerationJobStore:
    """regeneration_jobs 기반 — record↔row 변환. 메서드당 짧은 세션(get_db 패턴)."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal
    ) -> None:
        self._sf = session_factory

    async def create(self, record: RegenerationJobRecord) -> None:
        async with self._sf() as session:
            session.add(
                RegenerationJobRow(
                    id=record.id,
                    tenant_id=record.tenant_id,
                    campaign_id=record.campaign_id,
                    status=record.status.value,
                    selection_token=record.selection_token,
                    # 빈 리스트도 그대로 저장 — InMemory store와 동일 의미([] ↔ []) 유지.
                    candidates=record.candidates,
                    selected_candidate_id=record.selected_candidate_id,
                    proposal=record.proposal,
                    outcome_reason=record.outcome_reason,
                    error=record.error,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    started_at=record.started_at,
                    finished_at=record.finished_at,
                )
            )
            await session.commit()

    async def get(self, job_id: str) -> RegenerationJobRecord | None:
        async with self._sf() as session:
            row = await session.get(RegenerationJobRow, job_id)
        return _row_to_record(row) if row is not None else None

    async def save(self, record: RegenerationJobRecord) -> None:
        async with self._sf() as session:
            row = await session.get(RegenerationJobRow, record.id)
            if row is None:
                return
            row.status = record.status.value
            row.selection_token = record.selection_token
            row.candidates = record.candidates  # [] 그대로 — InMemory와 동일 의미
            row.selected_candidate_id = record.selected_candidate_id
            row.proposal = record.proposal
            row.outcome_reason = record.outcome_reason
            row.error = record.error
            row.updated_at = record.updated_at
            row.started_at = record.started_at
            row.finished_at = record.finished_at
            await session.commit()
