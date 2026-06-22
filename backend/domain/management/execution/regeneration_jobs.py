# 🅱 재생성 비동기 job — 상태 레코드 · 예외 · store Protocol · 인메모리 구현
"""채팅이 트리거한 재생성 job의 진행 상태를 보관한다. JobStatus는 A/B 계약이 아니라
job 레이어 로컬 관심사이므로 contracts가 아닌 여기에 둔다(설계 §2)."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_SELECTION = "awaiting_selection"
    PROPOSED = "proposed"
    OBSERVE = "observe"
    CREATIVE_UNAVAILABLE = "creative_unavailable"
    FAILED = "failed"


# ── 예외 (라우터가 HTTP 상태로 매핑) ──────────────────────────────
class JobNotFound(Exception):  # noqa: N818
    """job_id에 해당하는 행 없음 → 404."""


class JobTenantMismatch(Exception):  # noqa: N818
    """다른 테넌트의 job → 404(존재 노출 금지)."""


class JobNotAwaitingSelection(Exception):  # noqa: N818
    """선택 가능한 상태(AWAITING_SELECTION)가 아님 → 409."""


class CandidateNotInJob(Exception):  # noqa: N818
    """요청한 selected_id가 이 job의 후보에 없음 → 422."""


class SelectionContextExpired(Exception):  # noqa: N818
    """AWAITING_SELECTION이지만 agent._pending 소실(프로세스 재시작 등) → 409."""


@dataclass
class RegenerationJobRecord:
    id: str
    tenant_id: str
    campaign_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    selection_token: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    selected_candidate_id: str | None = None
    proposal: dict[str, Any] | None = None
    outcome_reason: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RegenerationJobStore(Protocol):
    async def create(self, record: RegenerationJobRecord) -> None: ...
    async def get(self, job_id: str) -> RegenerationJobRecord | None: ...
    async def save(self, record: RegenerationJobRecord) -> None: ...


class InMemoryRegenerationJobStore:
    """프로세스 메모리 store — v1 데모/테스트. get/save는 깊은 복사로 격리한다."""

    def __init__(self) -> None:
        self._rows: dict[str, RegenerationJobRecord] = {}

    async def create(self, record: RegenerationJobRecord) -> None:
        self._rows[record.id] = copy.deepcopy(record)

    async def get(self, job_id: str) -> RegenerationJobRecord | None:
        row = self._rows.get(job_id)
        return copy.deepcopy(row) if row is not None else None

    async def save(self, record: RegenerationJobRecord) -> None:
        self._rows[record.id] = copy.deepcopy(record)
