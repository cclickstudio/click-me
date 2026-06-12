"""🅱 내부 워크플로 상태머신 — 비동기 심사 보류 + 부분 실패 스냅샷 보존.

부분 실패 시 자동 롤백 없음 (P5 [안]): 플랫폼 객체 스냅샷을 기록하고 HALTED로 정지.
영속화(execution_runs 테이블)는 core/models.py 공동 설계 후 — 지금은 인메모리.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class RunStatus(StrEnum):
    RECEIVED = "received"
    VALIDATED = "validated"  # executor 4)~5)단계 통과
    RESERVED = "reserved"  # 6)단계 멱등키 선점 완료
    CALLING = "calling"  # 7)단계 Writer 호출 중 (재시도 포함)
    SUCCEEDED = "succeeded"
    PENDING_REVIEW = "pending_review"  # 실행은 했으나 플랫폼 비동기 심사 보류
    FAILED = "failed"
    HALTED = "halted"  # 부분 실패 — 스냅샷 기록 후 정지 (게이트 #7)


_TERMINAL: frozenset[RunStatus] = frozenset(
    {RunStatus.SUCCEEDED, RunStatus.PENDING_REVIEW, RunStatus.FAILED, RunStatus.HALTED}
)

_ALLOWED: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.RECEIVED: frozenset({RunStatus.VALIDATED, RunStatus.FAILED}),
    RunStatus.VALIDATED: frozenset({RunStatus.RESERVED, RunStatus.FAILED}),
    RunStatus.RESERVED: frozenset({RunStatus.CALLING, RunStatus.FAILED}),
    RunStatus.CALLING: frozenset(
        {RunStatus.SUCCEEDED, RunStatus.PENDING_REVIEW, RunStatus.FAILED, RunStatus.HALTED}
    ),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.PENDING_REVIEW: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.HALTED: frozenset(),
}


class IllegalTransitionError(RuntimeError):
    """허용되지 않은 상태 전이 — 실행 흐름 버그의 조기 신호."""


@dataclass
class ExecutionRun:
    """ApprovedAction 1건의 실행 기록 (재시도 포함)."""

    approval_id: str
    run_id: str = field(default_factory=lambda: str(uuid4()))
    status: RunStatus = RunStatus.RECEIVED
    attempts: int = 0
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    def record_attempt(self) -> None:
        self.attempts += 1

    def record_snapshot(self, snapshot: dict[str, Any]) -> None:
        """플랫폼 객체 스냅샷 보존 — 부분 실패 추적의 근거."""
        self.snapshots.append(snapshot)

    def advance(self, to: RunStatus, snapshot: dict[str, Any] | None = None) -> None:
        if to not in _ALLOWED[self.status]:
            raise IllegalTransitionError(f"{self.status} → {to} 전이는 허용되지 않음")
        if snapshot is not None:
            self.record_snapshot(snapshot)
        self.status = to
        if self.is_terminal:
            self.finished_at = datetime.now(UTC)
