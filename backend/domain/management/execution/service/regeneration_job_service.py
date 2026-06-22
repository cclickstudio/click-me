# 🅱 재생성 비동기 job 서비스 — start로 백그라운드 rank() 실행, select로 후보 확정
"""v1: in-process async job (uvicorn --workers 1 전제). RemediationAgent._pending이
인메모리라 rank·select는 같은 프로세스의 같은 agent 싱글톤에서 실행되어야 한다(설계 §2.3).
운영 확장은 SQS/Celery + worker 분리."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from domain.management.agents.outcome import OutcomeKind
from domain.management.execution.regeneration_jobs import (
    JobNotFound,
    JobStatus,
    RegenerationJobRecord,
)

if TYPE_CHECKING:
    from domain.management.execution.regeneration_jobs import RegenerationJobStore


class RegenerationJobService:
    def __init__(
        self,
        *,
        store: RegenerationJobStore,
        agent: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._agent = agent  # RemediationAgent 싱글톤 (rank/package)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._tasks: set[asyncio.Task] = set()

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
