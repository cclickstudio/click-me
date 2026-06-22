# 🅱 재생성 비동기 job 서비스 — start로 백그라운드 rank() 실행, select로 후보 확정
"""v1: in-process async job (uvicorn --workers 1 전제). RemediationAgent._pending이
인메모리라 rank·select는 같은 프로세스의 같은 agent 싱글톤에서 실행되어야 한다(설계 §2.3).
운영 확장은 SQS/Celery + worker 분리."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from domain.management.agents.outcome import OutcomeKind
from domain.management.execution.regeneration_jobs import (
    JobNotFound,
    JobStatus,
    RegenerationJobRecord,
)

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from domain.management.execution.regeneration_jobs import RegenerationJobStore


class RegenerationJobService:
    def __init__(
        self,
        *,
        store: RegenerationJobStore,
        agent: Any,
        clock: Callable[[], datetime] | None = None,
        scheduler: Callable[[Coroutine[Any, Any, None]], None] | None = None,
    ) -> None:
        self._store = store
        self._agent = agent  # RemediationAgent 싱글톤 (rank/package)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._scheduler = scheduler
        self._tasks: set[asyncio.Task] = set()

    # ── start — QUEUED 행 생성 + 백그라운드 스케줄 ──────────────────
    async def start(self, diagnosis: Any, context: Any) -> str:
        """QUEUED 행 생성 후 백그라운드 run_job 스케줄 → job_id 반환(즉답)."""
        job_id = uuid4().hex
        now = self._clock()
        await self._store.create(
            RegenerationJobRecord(
                id=job_id,
                tenant_id=diagnosis.tenant_id,
                campaign_id=diagnosis.campaign_id,
                status=JobStatus.QUEUED,
                created_at=now,
                updated_at=now,
            )
        )
        self._schedule(self.run_job(job_id, diagnosis, context))
        return job_id

    def _schedule(self, coro: Coroutine[Any, Any, None]) -> None:
        # 주입된 scheduler가 있으면 그것으로(테스트), 없으면 create_task + 레퍼런스 보관(GC 방지).
        if self._scheduler is not None:
            self._scheduler(coro)
            return
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ── run_job — rank() 결과를 job 상태로 매핑 ────────────────────
    async def run_job(self, job_id: str, diagnosis: Any, context: Any) -> None:
        """백그라운드 실행 본체. 절대 예외를 위로 올리지 않는다(task가 조용히 죽지 않게)."""
        try:
            rec = await self._require(job_id)
            rec.status = JobStatus.RUNNING
            rec.started_at = self._clock()
            await self._touch(rec)
            outcome = await self._agent.rank(diagnosis, context)
            await self._apply_outcome(job_id, outcome)
        except Exception as exc:  # noqa: BLE001 — 백그라운드 경계: 모든 실패를 FAILED 행으로 수렴
            await self._fail(job_id, repr(exc))

    async def _apply_outcome(self, job_id: str, outcome: Any) -> None:
        rec = await self._require(job_id)
        kind = outcome.kind
        if kind is OutcomeKind.AWAITING_SELECTION:
            rec.status = JobStatus.AWAITING_SELECTION
            rec.selection_token = outcome.selection_token
            rec.candidates = list(outcome.candidates or [])
        elif kind is OutcomeKind.PROPOSED and outcome.proposal is not None:
            rec.status = JobStatus.PROPOSED
            rec.proposal = outcome.proposal.model_dump(mode="json")
            rec.finished_at = self._clock()
        elif kind is OutcomeKind.OBSERVE:
            rec.status = JobStatus.OBSERVE
            rec.outcome_reason = outcome.reason.value if outcome.reason else None
            rec.finished_at = self._clock()
        elif kind is OutcomeKind.CREATIVE_UNAVAILABLE:
            rec.status = JobStatus.CREATIVE_UNAVAILABLE
            rec.outcome_reason = outcome.reason.value if outcome.reason else None
            rec.finished_at = self._clock()
        else:  # FAILED / INPUT_INVALID
            rec.status = JobStatus.FAILED
            rec.error = f"unexpected_outcome:{kind.value}"
            rec.finished_at = self._clock()
        await self._touch(rec)

    # ── 내부 헬퍼 ────────────────────────────────────────────────
    async def _require(self, job_id: str) -> RegenerationJobRecord:
        rec = await self._store.get(job_id)
        if rec is None:
            raise JobNotFound(job_id)
        return rec

    async def _touch(self, rec: RegenerationJobRecord) -> None:
        rec.updated_at = self._clock()
        await self._store.save(rec)

    async def _fail(self, job_id: str, error: str) -> None:
        rec = await self._store.get(job_id)
        if rec is None:
            return
        rec.status = JobStatus.FAILED
        rec.error = error
        rec.finished_at = self._clock()
        await self._touch(rec)
