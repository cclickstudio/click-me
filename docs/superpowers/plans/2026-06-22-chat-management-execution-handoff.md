# 채팅 ↔ 매니지먼트 실행·재생성 핸드오프 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 채팅(단일 매니지먼트 어시스턴트)이 🅱(실행·재생성) 기능을 부를 수 있도록, 재생성을 비동기 in-process job으로 돌리는 job 서비스·DB 상태·읽기 툴·라우터 엔드포인트를 만든다.

**Architecture:** `RegenerationJobService`(🅱 소유)가 `DiagnosisResult`를 받아 백그라운드로 `RemediationAgent.rank()`를 실행하고 상태를 `regeneration_jobs` 행에 남긴다. 후보 선택은 멱등한 `select()`로 진행하고, 승인·실행은 기존 REST·버튼 경로를 재사용한다. 어시스턴트 그래프의 `@tool` 등록(🅰 소유 파일)은 본 계획 범위 밖(소유권 보류) — 대신 🅱 소유의 tool-body 함수를 제공해 추후 🅰가 한 줄로 래핑한다.

**Tech Stack:** FastAPI · SQLAlchemy(async, NeonDB/Postgres) · LangGraph(기존 RemediationAgent) · pytest(asyncio_mode=auto) · Alembic.

**근거 설계 문서:** `docs/superpowers/specs/2026-06-22-chat-management-execution-handoff-design.md`

---

## File Structure

| 파일 | 책임 | 소유 |
|---|---|---|
| `backend/domain/management/execution/regeneration_jobs.py` (신규) | `JobStatus` enum · `RegenerationJobRecord` · 예외 5종 · `RegenerationJobStore` Protocol · `InMemoryRegenerationJobStore` | 🅱 |
| `backend/domain/management/execution/service/regeneration_job_service.py` (신규) | `RegenerationJobService` — start/run_job/get/select + 상태 매핑 + task set | 🅱 |
| `backend/domain/management/execution/assistant_tools.py` (신규) | 어시스턴트 tool-body 함수 (`start_regeneration`·`check_regeneration`·`execution_history`) | 🅱 |
| `backend/domain/management/execution/audit_log.py` (수정) | `AuditSink`에 `for_tenant` 추가 + `InMemoryAuditLog` 구현 | 🅱 |
| `backend/domain/management/execution/db_stores.py` (수정) | `DbRegenerationJobStore` 추가 + `DbAuditSink.for_tenant` 추가 | 🅱 |
| `backend/core/models.py` (수정) | `RegenerationJobRow` 테이블 | 🤝 공동 |
| `backend/alembic/versions/020_add_regeneration_jobs.py` (신규) | 마이그레이션 | 🤝 공동 |
| `backend/domain/management/wiring.py` (수정) | `build_regeneration_job_store` · `build_regeneration_job_service`(싱글톤) | 🅱 |
| `backend/api/routers/management.py` (수정) | `POST /regenerate/jobs` · `GET /regenerate/jobs/{id}` · `POST /regenerate/jobs/{id}/select` · `GET /execution/history` + 예외→HTTP 매핑 | 🤝 얇은 라우터 |
| `backend/tests/management/test_regeneration_jobs_store.py` (신규) | store 단위 테스트 | 🅱 |
| `backend/tests/management/test_regeneration_job_service.py` (신규) | service 단위 테스트 | 🅱 |
| `backend/tests/management/test_assistant_tools.py` (신규) | tool-body 단위 테스트 | 🅱 |

**v1 한계(설계 문서 §2.3 그대로):** in-process async job, `uvicorn --workers 1` 전제. 앱 재시작/멀티워커/서버 종료 시 실행 중 job 완료 미보장. `RemediationAgent._pending`이 인메모리라 rank·select는 같은 프로세스·같은 agent 싱글톤에서만 동작.

---

## Task 1: job 상태 모델 + 인메모리 store

**Files:**
- Create: `backend/domain/management/execution/regeneration_jobs.py`
- Test: `backend/tests/management/test_regeneration_jobs_store.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_regeneration_jobs_store.py`:

```python
# 🅱 재생성 job store 단위 테스트 — 상태 레코드 + 인메모리 CRUD
from datetime import UTC, datetime

from domain.management.execution.regeneration_jobs import (
    InMemoryRegenerationJobStore,
    JobStatus,
    RegenerationJobRecord,
)

NOW = datetime(2026, 6, 22, 9, 0, tzinfo=UTC)


def _record(job_id: str = "job-1", tenant_id: str = "org-1") -> RegenerationJobRecord:
    return RegenerationJobRecord(
        id=job_id,
        tenant_id=tenant_id,
        campaign_id="camp-1",
        status=JobStatus.QUEUED,
        created_at=NOW,
        updated_at=NOW,
    )


async def test_create_then_get_returns_same_record():
    store = InMemoryRegenerationJobStore()
    await store.create(_record())
    got = await store.get("job-1")
    assert got is not None
    assert got.id == "job-1"
    assert got.status is JobStatus.QUEUED


async def test_get_missing_returns_none():
    store = InMemoryRegenerationJobStore()
    assert await store.get("nope") is None


async def test_save_persists_mutation():
    store = InMemoryRegenerationJobStore()
    rec = _record()
    await store.create(rec)
    rec.status = JobStatus.RUNNING
    rec.started_at = NOW
    await store.save(rec)
    got = await store.get("job-1")
    assert got.status is JobStatus.RUNNING
    assert got.started_at == NOW


async def test_get_returns_copy_not_live_reference():
    # store가 내부 객체를 그대로 노출하면 호출자가 저장 없이 상태를 바꿔버릴 수 있다.
    store = InMemoryRegenerationJobStore()
    await store.create(_record())
    got = await store.get("job-1")
    got.status = JobStatus.FAILED
    again = await store.get("job-1")
    assert again.status is JobStatus.QUEUED
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_regeneration_jobs_store.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.management.execution.regeneration_jobs`

- [ ] **Step 3: 구현**

`backend/domain/management/execution/regeneration_jobs.py`:

```python
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
class JobNotFound(Exception):
    """job_id에 해당하는 행 없음 → 404."""


class JobTenantMismatch(Exception):
    """다른 테넌트의 job → 404(존재 노출 금지)."""


class JobNotAwaitingSelection(Exception):
    """선택 가능한 상태(AWAITING_SELECTION)가 아님 → 409."""


class CandidateNotInJob(Exception):
    """요청한 selected_id가 이 job의 후보에 없음 → 422."""


class SelectionContextExpired(Exception):
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
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_regeneration_jobs_store.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format domain/management/execution/regeneration_jobs.py tests/management/test_regeneration_jobs_store.py && uv run ruff check domain/management/execution/regeneration_jobs.py tests/management/test_regeneration_jobs_store.py --fix
git add domain/management/execution/regeneration_jobs.py tests/management/test_regeneration_jobs_store.py
git commit -m "add: 재생성 job 상태 레코드 + 인메모리 store"
```

---

## Task 2: job 서비스 — run_job 상태 매핑

**Files:**
- Create: `backend/domain/management/execution/service/regeneration_job_service.py`
- Test: `backend/tests/management/test_regeneration_job_service.py`

run_job은 `RemediationAgent.rank()` 결과(`RemediationOutcome`)를 job 상태로 매핑한다. `rank()`는 예외를 올리지 않고 FAILED outcome을 돌려주므로(`regeneration.py`), 매핑 표가 곧 진실의 원천이다.

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_regeneration_job_service.py`:

```python
# 🅱 재생성 job 서비스 — run_job 상태 매핑 + start + select 멱등
from datetime import UTC, datetime

from domain.management.agents.outcome import OutcomeKind, OutcomeReason, RemediationOutcome
from domain.management.execution.regeneration_jobs import (
    InMemoryRegenerationJobStore,
    JobStatus,
)
from domain.management.execution.service.regeneration_job_service import (
    RegenerationJobService,
)

NOW = datetime(2026, 6, 22, 9, 0, tzinfo=UTC)


class _FakeAgent:
    """rank/package를 미리 정한 outcome으로 대체하는 가짜 RemediationAgent."""

    def __init__(self, rank_outcome=None, package_outcome=None):
        self._rank = rank_outcome
        self._package = package_outcome
        self.rank_calls = 0
        self.package_calls: list[tuple] = []

    async def rank(self, diagnosis, context):
        self.rank_calls += 1
        return self._rank

    async def package(self, token, *, tenant_id, selected_id):
        self.package_calls.append((token, tenant_id, selected_id))
        return self._package


def _service(agent) -> RegenerationJobService:
    return RegenerationJobService(
        store=InMemoryRegenerationJobStore(), agent=agent, clock=lambda: NOW
    )


async def _seed_queued(svc, job_id="job-1", tenant_id="org-1"):
    from domain.management.execution.regeneration_jobs import RegenerationJobRecord

    await svc._store.create(
        RegenerationJobRecord(
            id=job_id,
            tenant_id=tenant_id,
            campaign_id="camp-1",
            status=JobStatus.QUEUED,
            created_at=NOW,
            updated_at=NOW,
        )
    )


async def test_run_job_awaiting_selection_stores_candidates_and_token():
    outcome = RemediationOutcome(
        kind=OutcomeKind.AWAITING_SELECTION,
        selection_token="tok-1",
        candidates=[{"candidate_id": "c1"}, {"candidate_id": "c2"}],
    )
    svc = _service(_FakeAgent(rank_outcome=outcome))
    await _seed_queued(svc)
    await svc.run_job("job-1", diagnosis=None, context=None)
    rec = await svc._store.get("job-1")
    assert rec.status is JobStatus.AWAITING_SELECTION
    assert rec.selection_token == "tok-1"
    assert [c["candidate_id"] for c in rec.candidates] == ["c1", "c2"]
    assert rec.started_at == NOW


async def test_run_job_observe_stores_reason():
    outcome = RemediationOutcome(kind=OutcomeKind.OBSERVE, reason=OutcomeReason.LOW_CONFIDENCE)
    svc = _service(_FakeAgent(rank_outcome=outcome))
    await _seed_queued(svc)
    await svc.run_job("job-1", diagnosis=None, context=None)
    rec = await svc._store.get("job-1")
    assert rec.status is JobStatus.OBSERVE
    assert rec.outcome_reason == OutcomeReason.LOW_CONFIDENCE.value
    assert rec.finished_at == NOW


async def test_run_job_creative_unavailable_stores_reason():
    outcome = RemediationOutcome(
        kind=OutcomeKind.CREATIVE_UNAVAILABLE, reason=OutcomeReason.GENERATOR_EMPTY
    )
    svc = _service(_FakeAgent(rank_outcome=outcome))
    await _seed_queued(svc)
    await svc.run_job("job-1", diagnosis=None, context=None)
    rec = await svc._store.get("job-1")
    assert rec.status is JobStatus.CREATIVE_UNAVAILABLE
    assert rec.outcome_reason == OutcomeReason.GENERATOR_EMPTY.value


async def test_run_job_failed_outcome_marks_failed():
    outcome = RemediationOutcome(kind=OutcomeKind.FAILED)
    svc = _service(_FakeAgent(rank_outcome=outcome))
    await _seed_queued(svc)
    await svc.run_job("job-1", diagnosis=None, context=None)
    rec = await svc._store.get("job-1")
    assert rec.status is JobStatus.FAILED
    assert rec.error


async def test_run_job_swallows_exception_and_marks_failed():
    class _Boom:
        async def rank(self, *a, **k):
            raise RuntimeError("boom")

    svc = _service(_Boom())
    await _seed_queued(svc)
    await svc.run_job("job-1", diagnosis=None, context=None)  # 예외가 새어나오면 실패
    rec = await svc._store.get("job-1")
    assert rec.status is JobStatus.FAILED
    assert "boom" in rec.error
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_regeneration_job_service.py -v`
Expected: FAIL — `ModuleNotFoundError: ...regeneration_job_service`

- [ ] **Step 3: 구현 (run_job + 매핑까지)**

`backend/domain/management/execution/service/regeneration_job_service.py`:

```python
# 🅱 재생성 비동기 job 서비스 — start로 백그라운드 rank() 실행, select로 후보 확정
"""v1: in-process async job (uvicorn --workers 1 전제). RemediationAgent._pending이
인메모리라 rank·select는 같은 프로세스의 같은 agent 싱글톤에서 실행되어야 한다(설계 §2.3).
운영 확장은 SQS/Celery + worker 분리."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from domain.management.agents.outcome import OutcomeKind
from domain.management.execution.regeneration_jobs import (
    CandidateNotInJob,
    JobNotAwaitingSelection,
    JobNotFound,
    JobStatus,
    JobTenantMismatch,
    RegenerationJobRecord,
    SelectionContextExpired,
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
        self._scheduler = scheduler  # None이면 asyncio.create_task
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
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_regeneration_job_service.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format domain/management/execution/service/regeneration_job_service.py tests/management/test_regeneration_job_service.py && uv run ruff check domain/management/execution/service/regeneration_job_service.py tests/management/test_regeneration_job_service.py --fix
git add domain/management/execution/service/regeneration_job_service.py tests/management/test_regeneration_job_service.py
git commit -m "add: 재생성 job 서비스 run_job 상태 매핑"
```

---

## Task 3: job 서비스 — start (QUEUED + 스케줄)

**Files:**
- Modify: `backend/domain/management/execution/service/regeneration_job_service.py`
- Test: `backend/tests/management/test_regeneration_job_service.py` (추가)

- [ ] **Step 1: 실패 테스트 추가**

`test_regeneration_job_service.py` 끝에 추가:

```python
async def test_start_creates_queued_row_and_schedules():
    scheduled: list = []
    svc = RegenerationJobService(
        store=InMemoryRegenerationJobStore(),
        agent=_FakeAgent(),
        clock=lambda: NOW,
        scheduler=lambda coro: scheduled.append(coro),  # create_task 대신 캡처
    )

    class _Dx:
        tenant_id = "org-9"
        campaign_id = "camp-9"

    job_id = await svc.start(_Dx(), context=None)
    rec = await svc._store.get(job_id)
    assert rec is not None
    assert rec.status is JobStatus.QUEUED
    assert rec.tenant_id == "org-9"
    assert rec.campaign_id == "camp-9"
    assert len(scheduled) == 1  # run_job 코루틴이 스케줄됨

    await scheduled[0]  # 캡처한 코루틴을 닫아 RuntimeWarning 방지
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_regeneration_job_service.py::test_start_creates_queued_row_and_schedules -v`
Expected: FAIL — `AttributeError: 'RegenerationJobService' object has no attribute 'start'`

- [ ] **Step 3: 구현 — start + _schedule 추가**

`regeneration_job_service.py`의 `run_job` 정의 **앞에** 추가:

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_regeneration_job_service.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format domain/management/execution/service/regeneration_job_service.py tests/management/test_regeneration_job_service.py && uv run ruff check domain/management/execution/service/regeneration_job_service.py tests/management/test_regeneration_job_service.py --fix
git add domain/management/execution/service/regeneration_job_service.py tests/management/test_regeneration_job_service.py
git commit -m "add: 재생성 job start — QUEUED 행 + 백그라운드 스케줄"
```

---

## Task 4: job 서비스 — select (멱등·검증·_pending 소실)

**Files:**
- Modify: `backend/domain/management/execution/service/regeneration_job_service.py`
- Test: `backend/tests/management/test_regeneration_job_service.py` (추가)

select 절차(설계 §2.5): 조회→tenant→status→candidate 검증→package→저장. 같은 선택은 멱등, 다른 선택은 409.

- [ ] **Step 1: 실패 테스트 추가**

```python
async def _seed_awaiting(svc, *, tenant_id="org-1", token="tok-1"):
    from domain.management.execution.regeneration_jobs import RegenerationJobRecord

    await svc._store.create(
        RegenerationJobRecord(
            id="job-1",
            tenant_id=tenant_id,
            campaign_id="camp-1",
            status=JobStatus.AWAITING_SELECTION,
            created_at=NOW,
            updated_at=NOW,
            selection_token=token,
            candidates=[{"candidate_id": "c1"}, {"candidate_id": "c2"}],
        )
    )


async def test_select_packages_and_marks_proposed():
    from domain.management.execution.regeneration_jobs import RegenerationJobRecord  # noqa: F401

    class _Proposal:
        def model_dump(self, mode="json"):
            return {"proposal_id": "p1"}

    from domain.management.agents.outcome import RemediationOutcome

    pkg = RemediationOutcome(kind=OutcomeKind.PROPOSED, proposal=_Proposal())
    agent = _FakeAgent(package_outcome=pkg)
    svc = _service(agent)
    await _seed_awaiting(svc)
    rec = await svc.select("job-1", "c1", tenant_id="org-1")
    assert rec.status is JobStatus.PROPOSED
    assert rec.selected_candidate_id == "c1"
    assert rec.proposal == {"proposal_id": "p1"}
    assert agent.package_calls == [("tok-1", "org-1", "c1")]


async def test_select_same_candidate_is_idempotent():
    from domain.management.agents.outcome import RemediationOutcome

    class _Proposal:
        def model_dump(self, mode="json"):
            return {"proposal_id": "p1"}

    agent = _FakeAgent(package_outcome=RemediationOutcome(kind=OutcomeKind.PROPOSED, proposal=_Proposal()))
    svc = _service(agent)
    await _seed_awaiting(svc)
    await svc.select("job-1", "c1", tenant_id="org-1")
    rec = await svc.select("job-1", "c1", tenant_id="org-1")  # 재시도
    assert rec.status is JobStatus.PROPOSED
    assert len(agent.package_calls) == 1  # package는 한 번만(멱등)


async def test_select_different_candidate_after_proposed_raises_409():
    from domain.management.agents.outcome import RemediationOutcome

    class _Proposal:
        def model_dump(self, mode="json"):
            return {"proposal_id": "p1"}

    agent = _FakeAgent(package_outcome=RemediationOutcome(kind=OutcomeKind.PROPOSED, proposal=_Proposal()))
    svc = _service(agent)
    await _seed_awaiting(svc)
    await svc.select("job-1", "c1", tenant_id="org-1")
    import pytest

    from domain.management.execution.regeneration_jobs import JobNotAwaitingSelection

    with pytest.raises(JobNotAwaitingSelection):
        await svc.select("job-1", "c2", tenant_id="org-1")


async def test_select_unknown_candidate_raises_422():
    import pytest

    from domain.management.execution.regeneration_jobs import CandidateNotInJob

    svc = _service(_FakeAgent())
    await _seed_awaiting(svc)
    with pytest.raises(CandidateNotInJob):
        await svc.select("job-1", "c9", tenant_id="org-1")


async def test_select_other_tenant_raises_404():
    import pytest

    from domain.management.execution.regeneration_jobs import JobTenantMismatch

    svc = _service(_FakeAgent())
    await _seed_awaiting(svc, tenant_id="org-1")
    with pytest.raises(JobTenantMismatch):
        await svc.select("job-1", "c1", tenant_id="org-OTHER")


async def test_select_missing_pending_raises_selection_expired():
    import pytest

    from domain.management.agents.outcome import RemediationOutcome
    from domain.management.execution.regeneration_jobs import SelectionContextExpired

    # _pending 소실 시 package는 PROPOSED가 아닌 결과를 돌려준다(INPUT_INVALID).
    agent = _FakeAgent(package_outcome=RemediationOutcome(kind=OutcomeKind.INPUT_INVALID))
    svc = _service(agent)
    await _seed_awaiting(svc)
    with pytest.raises(SelectionContextExpired):
        await svc.select("job-1", "c1", tenant_id="org-1")
    rec = await svc._store.get("job-1")
    assert rec.status is JobStatus.AWAITING_SELECTION  # FAILED로 덮지 않음(설계 §2.3)


async def test_get_other_tenant_raises_404():
    import pytest

    from domain.management.execution.regeneration_jobs import JobTenantMismatch

    svc = _service(_FakeAgent())
    await _seed_awaiting(svc, tenant_id="org-1")
    with pytest.raises(JobTenantMismatch):
        await svc.get("job-1", tenant_id="org-OTHER")
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_regeneration_job_service.py -k "select or get_other" -v`
Expected: FAIL — `AttributeError: ... has no attribute 'select'`

- [ ] **Step 3: 구현 — get + select 추가**

`regeneration_job_service.py`의 `_require` **앞에**(public 메서드 영역) 추가:

```python
    async def get(self, job_id: str, *, tenant_id: str) -> RegenerationJobRecord:
        """tenant 검증 포함 조회. 다른 테넌트면 404(존재 노출 금지)."""
        rec = await self._require(job_id)
        if rec.tenant_id != tenant_id:
            raise JobTenantMismatch(job_id)
        return rec

    async def select(
        self, job_id: str, selected_id: str, *, tenant_id: str
    ) -> RegenerationJobRecord:
        rec = await self.get(job_id, tenant_id=tenant_id)  # 1·2. 조회 + tenant
        # 3. status — 멱등/충돌 처리
        if rec.status is JobStatus.PROPOSED:
            if rec.selected_candidate_id == selected_id:
                return rec  # 같은 선택 재시도 → 저장된 proposal 멱등 반환
            raise JobNotAwaitingSelection(job_id)  # 다른 선택 → 409
        if rec.status is not JobStatus.AWAITING_SELECTION:
            raise JobNotAwaitingSelection(job_id)
        # 4. candidate 멤버십(1차 방어 — package의 claim이 2차)
        if selected_id not in {c.get("candidate_id") for c in rec.candidates}:
            raise CandidateNotInJob(selected_id)
        # 5. package — _pending 소실 시 PROPOSED가 아닌 결과 → 409
        outcome = await self._agent.package(
            rec.selection_token, tenant_id=tenant_id, selected_id=selected_id
        )
        if outcome.kind is not OutcomeKind.PROPOSED or outcome.proposal is None:
            raise SelectionContextExpired(job_id)  # job.status는 AWAITING_SELECTION 유지
        # 6. 저장
        rec.status = JobStatus.PROPOSED
        rec.selected_candidate_id = selected_id
        rec.proposal = outcome.proposal.model_dump(mode="json")
        rec.finished_at = self._clock()
        await self._touch(rec)
        return rec
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_regeneration_job_service.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format domain/management/execution/service/regeneration_job_service.py tests/management/test_regeneration_job_service.py && uv run ruff check domain/management/execution/service/regeneration_job_service.py tests/management/test_regeneration_job_service.py --fix
git add domain/management/execution/service/regeneration_job_service.py tests/management/test_regeneration_job_service.py
git commit -m "add: 재생성 job select — 멱등·이중검증·_pending 소실 처리"
```

---

## Task 5: audit_log에 for_tenant 추가 (execution_history 토대)

**Files:**
- Modify: `backend/domain/management/execution/audit_log.py`
- Test: `backend/tests/management/test_regeneration_jobs_store.py` (audit 테스트 추가) — 또는 신규 작은 테스트 파일

`execution_history`는 테넌트 단위 실행 이벤트를 읽어야 한다. 현재 `AuditSink`는 `for_approval`만 있다. tenant 단위 조회 메서드를 추가한다.

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_audit_for_tenant.py`:

```python
# 🅱 감사 로그 테넌트 단위 조회 — execution_history 토대
from datetime import UTC, datetime

from domain.management.execution.audit_log import AuditEvent, InMemoryAuditLog


async def test_for_tenant_returns_only_that_tenant_in_time_order():
    log = InMemoryAuditLog()
    await log.append(
        AuditEvent(category="executor.completed", tenant_id="org-1", approval_id="a1")
    )
    await log.append(
        AuditEvent(category="executor.completed", tenant_id="org-2", approval_id="a2")
    )
    await log.append(
        AuditEvent(category="executor.rejected", tenant_id="org-1", approval_id="a3")
    )
    events = await log.for_tenant("org-1")
    assert [e.approval_id for e in events] == ["a1", "a3"]
    assert all(e.tenant_id == "org-1" for e in events)


async def test_for_tenant_empty_when_none_match():
    log = InMemoryAuditLog()
    await log.append(AuditEvent(category="x", tenant_id="org-1"))
    assert await log.for_tenant("org-zzz") == ()
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_audit_for_tenant.py -v`
Expected: FAIL — `AttributeError: 'InMemoryAuditLog' object has no attribute 'for_tenant'`

- [ ] **Step 3: 구현**

`audit_log.py`의 `AuditSink` Protocol에 메서드 추가:

```python
class AuditSink(Protocol):
    async def append(self, event: AuditEvent) -> None: ...

    async def for_approval(self, approval_id: str) -> tuple[AuditEvent, ...]: ...

    async def for_tenant(self, tenant_id: str) -> tuple[AuditEvent, ...]: ...
```

`InMemoryAuditLog`에 메서드 추가(`for_approval` 아래):

```python
    async def for_tenant(self, tenant_id: str) -> tuple[AuditEvent, ...]:
        """테넌트 단위 실행 이력 — execution_history(읽기) 토대. 삽입 순서(=시간순) 유지."""
        return tuple(e for e in self._events if e.tenant_id == tenant_id)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_audit_for_tenant.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format domain/management/execution/audit_log.py tests/management/test_audit_for_tenant.py && uv run ruff check domain/management/execution/audit_log.py tests/management/test_audit_for_tenant.py --fix
git add domain/management/execution/audit_log.py tests/management/test_audit_for_tenant.py
git commit -m "add: 감사 로그 for_tenant — execution_history 토대"
```

---

## Task 6: 어시스턴트 tool-body 함수 (🅱 소유)

**Files:**
- Create: `backend/domain/management/execution/assistant_tools.py`
- Test: `backend/tests/management/test_assistant_tools.py`

🅰가 `@tool`로 래핑할 함수들. settings + job 서비스 + audit를 받아 dict를 돌려준다(어시스턴트 그래프의 `live_tools.*` 패턴과 동일). detection 호출은 여기 두지 않는다 — start_regeneration은 **이미 만들어진 DiagnosisResult를 받는 오케스트레이터에서** 호출되며, 이 함수는 job 서비스에 위임만 한다(설계 §1 경계).

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_assistant_tools.py`:

```python
# 🅱 어시스턴트 tool-body — job 서비스/audit에 위임하는 dict 반환 함수
from datetime import UTC, datetime

from domain.management.execution.assistant_tools import (
    check_regeneration,
    execution_history,
)
from domain.management.execution.audit_log import AuditEvent, InMemoryAuditLog
from domain.management.execution.regeneration_jobs import (
    InMemoryRegenerationJobStore,
    JobStatus,
    RegenerationJobRecord,
)
from domain.management.execution.service.regeneration_job_service import (
    RegenerationJobService,
)

NOW = datetime(2026, 6, 22, 9, 0, tzinfo=UTC)


async def test_check_regeneration_awaiting_returns_candidates():
    store = InMemoryRegenerationJobStore()
    await store.create(
        RegenerationJobRecord(
            id="job-1",
            tenant_id="org-1",
            campaign_id="camp-1",
            status=JobStatus.AWAITING_SELECTION,
            created_at=NOW,
            updated_at=NOW,
            candidates=[{"candidate_id": "c1"}],
        )
    )
    svc = RegenerationJobService(store=store, agent=None, clock=lambda: NOW)
    out = await check_regeneration(svc, "job-1", tenant_id="org-1")
    assert out["status"] == "awaiting_selection"
    assert out["candidates"] == [{"candidate_id": "c1"}]


async def test_check_regeneration_other_tenant_returns_error_not_raise():
    store = InMemoryRegenerationJobStore()
    await store.create(
        RegenerationJobRecord(
            id="job-1",
            tenant_id="org-1",
            campaign_id="camp-1",
            status=JobStatus.RUNNING,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    svc = RegenerationJobService(store=store, agent=None, clock=lambda: NOW)
    out = await check_regeneration(svc, "job-1", tenant_id="org-OTHER")
    assert out["error"] == "not_found"  # 어시스턴트는 예외 대신 표면화


async def test_execution_history_filters_by_tenant():
    log = InMemoryAuditLog()
    await log.append(AuditEvent(category="executor.completed", tenant_id="org-1", approval_id="a1"))
    await log.append(AuditEvent(category="executor.completed", tenant_id="org-2", approval_id="a2"))
    out = await execution_history(log, tenant_id="org-1")
    assert out["count"] == 1
    assert out["events"][0]["approval_id"] == "a1"
    assert out["events"][0]["category"] == "executor.completed"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_assistant_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: ...assistant_tools`

- [ ] **Step 3: 구현**

`backend/domain/management/execution/assistant_tools.py`:

```python
# 🅱 어시스턴트 tool-body — 채팅 그래프(🅰)가 @tool로 래핑할 위임 함수들
"""숫자·상태는 여기서(실측·DB) 나온다. 어시스턴트는 예외를 던지지 않고 dict로 표면화한다.
start_regeneration은 이미 만들어진 DiagnosisResult를 받는 오케스트레이터에서 호출된다 —
detection(🅰) 호출은 이 모듈이 하지 않는다(설계 §1 경계)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.management.execution.regeneration_jobs import (
    JobNotFound,
    JobTenantMismatch,
)

if TYPE_CHECKING:
    from domain.management.execution.audit_log import AuditSink
    from domain.management.execution.service.regeneration_job_service import (
        RegenerationJobService,
    )


async def start_regeneration(
    service: RegenerationJobService, diagnosis: Any, context: Any
) -> dict:
    """재생성 비동기 job 시작 → {job_id, status:"queued"} 즉답. 무거운 생성은 백그라운드."""
    job_id = await service.start(diagnosis, context)
    return {"job_id": job_id, "status": "queued"}


async def check_regeneration(
    service: RegenerationJobService, job_id: str, *, tenant_id: str
) -> dict:
    """job 진행 상태 조회. AWAITING_SELECTION이면 후보 목록 포함."""
    try:
        rec = await service.get(job_id, tenant_id=tenant_id)
    except (JobNotFound, JobTenantMismatch):
        return {"error": "not_found"}
    out: dict[str, Any] = {"job_id": rec.id, "status": rec.status.value}
    if rec.candidates:
        out["candidates"] = rec.candidates
    if rec.proposal:
        out["proposal"] = rec.proposal
    if rec.outcome_reason:
        out["outcome_reason"] = rec.outcome_reason
    return out


async def execution_history(audit: AuditSink, *, tenant_id: str, limit: int = 20) -> dict:
    """테넌트의 최근 실행 감사 이벤트 요약(읽기). org 스코프 강제.

    v1은 테넌트 단위. 캠페인 정밀 필터는 감사 이벤트에 campaign_id가 실린 뒤 후속(설계 §5.3).
    """
    events = await audit.for_tenant(tenant_id)
    rows = [
        {
            "category": e.category,
            "approval_id": e.approval_id,
            "occurred_at": e.occurred_at.isoformat(),
        }
        for e in events[-limit:]
    ]
    return {"count": len(rows), "events": rows}
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_assistant_tools.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format domain/management/execution/assistant_tools.py tests/management/test_assistant_tools.py && uv run ruff check domain/management/execution/assistant_tools.py tests/management/test_assistant_tools.py --fix
git add domain/management/execution/assistant_tools.py tests/management/test_assistant_tools.py
git commit -m "add: 어시스턴트 tool-body (start/check 재생성·execution_history)"
```

---

## Task 7: DB 모델 + 마이그레이션 + DB store (🤝 공동)

**Files:**
- Modify: `backend/core/models.py`
- Create: `backend/alembic/versions/020_add_regeneration_jobs.py`
- Modify: `backend/domain/management/execution/db_stores.py`
- Modify: `backend/domain/management/execution/audit_log.py` (DbAuditSink는 db_stores에 있음 — 아래 참조)
- Test: `backend/tests/management/test_db_regeneration_job_store.py`

> ⚠️ 🤝 DB 스키마 변경 — 머지 전 `down_revision`(head 라인) + 컬럼을 🅰와 합의(CLAUDE.md 협업 규칙). 본 태스크는 코드까지 준비하되 머지는 합의 후.

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_db_regeneration_job_store.py`:

```python
# 🅱 DB 재생성 job store — Protocol 준수 + record↔row 변환 (라이브 DB 불필요한 단위 검증)
from datetime import UTC, datetime

from domain.management.execution.db_stores import DbRegenerationJobStore, _row_to_record
from core.models import RegenerationJobRow
from domain.management.execution.regeneration_jobs import JobStatus, RegenerationJobStore

NOW = datetime(2026, 6, 22, 9, 0, tzinfo=UTC)


def test_db_store_satisfies_protocol():
    store: RegenerationJobStore = DbRegenerationJobStore()
    assert hasattr(store, "create") and hasattr(store, "get") and hasattr(store, "save")


def test_row_to_record_maps_fields():
    row = RegenerationJobRow(
        id="job-1",
        tenant_id="org-1",
        campaign_id="camp-1",
        status="awaiting_selection",
        selection_token="tok-1",
        candidates=[{"candidate_id": "c1"}],
        created_at=NOW,
        updated_at=NOW,
    )
    rec = _row_to_record(row)
    assert rec.id == "job-1"
    assert rec.status is JobStatus.AWAITING_SELECTION
    assert rec.candidates == [{"candidate_id": "c1"}]
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_db_regeneration_job_store.py -v`
Expected: FAIL — `ImportError: cannot import name 'RegenerationJobRow'`

- [ ] **Step 3a: 모델 추가**

`backend/core/models.py`의 `IdempotencyKeyRow` 아래에 추가(기존 import: `Mapped, mapped_column, String, Integer, JSONB, UUID, DateTime, func, uuid, datetime` 사용 — 파일 상단 동일 패턴):

```python
class RegenerationJobRow(Base):
    """🅱 채팅이 트리거한 재생성 비동기 job 상태(설계 2026-06-22). v1 in-process 전제."""

    __tablename__ = "regeneration_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    campaign_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    selection_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    candidates: Mapped[dict | None] = mapped_column(JSONB)  # list[dict]를 JSON으로
    selected_candidate_id: Mapped[str | None] = mapped_column(String(64))
    proposal: Mapped[dict | None] = mapped_column(JSONB)
    outcome_reason: Mapped[str | None] = mapped_column(String(48))
    error: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 3b: 마이그레이션 작성**

`backend/alembic/versions/020_add_regeneration_jobs.py`:

```python
"""add regeneration_jobs table — 채팅 트리거 재생성 비동기 job 상태

Revision ID: 020
Revises: 019
Create Date: 2026-06-22

core/models.py의 RegenerationJobRow와 1:1. v1 in-process job(설계 2026-06-22 §2).
⚠️ 🤝 DB 스키마 변경 — 머지 전 down_revision(head 라인) 합의 필요(CLAUDE.md 협업 규칙).
"""

from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS regeneration_jobs (
            id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            campaign_id VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            selection_token VARCHAR(64) UNIQUE,
            candidates JSONB,
            selected_candidate_id VARCHAR(64),
            proposal JSONB,
            outcome_reason VARCHAR(48),
            error VARCHAR(512),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_regen_jobs_tenant ON regeneration_jobs (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_regen_jobs_campaign ON regeneration_jobs (campaign_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_regen_jobs_status ON regeneration_jobs (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_regen_jobs_created ON regeneration_jobs (created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS regeneration_jobs")
```

- [ ] **Step 3c: DB store 구현**

`backend/domain/management/execution/db_stores.py` 상단 import에 추가:

```python
from core.models import AuditEventRow, IdempotencyKeyRow, RegenerationJobRow
from domain.management.execution.regeneration_jobs import JobStatus, RegenerationJobRecord
```

파일 끝에 추가:

```python
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
                    candidates=record.candidates or None,
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
            row = await session.get(RegenerationJobRow, job_id := record.id)
            if row is None:
                return
            row.status = record.status.value
            row.selection_token = record.selection_token
            row.candidates = record.candidates or None
            row.selected_candidate_id = record.selected_candidate_id
            row.proposal = record.proposal
            row.outcome_reason = record.outcome_reason
            row.error = record.error
            row.updated_at = record.updated_at
            row.started_at = record.started_at
            row.finished_at = record.finished_at
            await session.commit()
```

- [ ] **Step 3d: DbAuditSink.for_tenant 추가**

`db_stores.py`의 `DbAuditSink` 안에 `for_approval` 아래로 추가:

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_db_regeneration_job_store.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format core/models.py domain/management/execution/db_stores.py alembic/versions/020_add_regeneration_jobs.py tests/management/test_db_regeneration_job_store.py && uv run ruff check core/models.py domain/management/execution/db_stores.py alembic/versions/020_add_regeneration_jobs.py tests/management/test_db_regeneration_job_store.py --fix
git add core/models.py domain/management/execution/db_stores.py alembic/versions/020_add_regeneration_jobs.py tests/management/test_db_regeneration_job_store.py
git commit -m "add: regeneration_jobs 테이블·마이그레이션·DB store + audit for_tenant"
```

---

## Task 8: wiring 빌더 (싱글톤 service)

**Files:**
- Modify: `backend/domain/management/wiring.py`
- Test: `backend/tests/management/test_regeneration_job_wiring.py`

`RemediationAgent._pending`이 인메모리라 **service는 프로세스 싱글톤**이어야 한다(rank·select 같은 인스턴스). wiring에서 모듈 전역 싱글톤으로 보관한다.

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_regeneration_job_wiring.py`:

```python
# 🅱 재생성 job wiring — 싱글톤 service + use_mock store 분기
from domain.management.execution.regeneration_jobs import InMemoryRegenerationJobStore
from domain.management.execution.service.regeneration_job_service import (
    RegenerationJobService,
)
from domain.management.wiring import (
    build_regeneration_job_service,
    build_regeneration_job_store,
)


class _Settings:
    use_mock = True


def test_store_is_inmemory_when_mock():
    store = build_regeneration_job_store(_Settings())
    assert isinstance(store, InMemoryRegenerationJobStore)


def test_service_is_singleton():
    a = build_regeneration_job_service(_Settings())
    b = build_regeneration_job_service(_Settings())
    assert isinstance(a, RegenerationJobService)
    assert a is b  # 같은 인스턴스(_pending 보존)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_regeneration_job_wiring.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_regeneration_job_service'`

- [ ] **Step 3: 구현**

`backend/domain/management/wiring.py` 끝에 추가:

```python
def build_regeneration_job_store(settings):
    """재생성 job store — use_mock이면 인메모리, 아니면 DB(regeneration_jobs)."""
    if getattr(settings, "use_mock", True):
        from domain.management.execution.regeneration_jobs import (  # noqa: PLC0415
            InMemoryRegenerationJobStore,
        )

        return InMemoryRegenerationJobStore()
    from domain.management.execution.db_stores import (  # noqa: PLC0415
        DbRegenerationJobStore,
    )

    return DbRegenerationJobStore()


#: 재생성 job 서비스 싱글톤 — RemediationAgent._pending이 인메모리라 프로세스 1개로 고정.
_regeneration_job_service = None


def build_regeneration_job_service(settings):
    """프로세스 싱글톤. rank·select가 같은 agent 인스턴스를 공유해야 한다(설계 §2.3)."""
    global _regeneration_job_service  # noqa: PLW0603
    if _regeneration_job_service is None:
        from domain.management.agents.regeneration_tools import (  # noqa: PLC0415
            build_regeneration_agent,
        )
        from domain.management.execution.service.regeneration_job_service import (  # noqa: PLC0415
            RegenerationJobService,
        )

        _regeneration_job_service = RegenerationJobService(
            store=build_regeneration_job_store(settings),
            agent=build_regeneration_agent(),  # 키 없으면 결정론 폴백
        )
    return _regeneration_job_service
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_regeneration_job_wiring.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format domain/management/wiring.py tests/management/test_regeneration_job_wiring.py && uv run ruff check domain/management/wiring.py tests/management/test_regeneration_job_wiring.py --fix
git add domain/management/wiring.py tests/management/test_regeneration_job_wiring.py
git commit -m "add: 재생성 job wiring — 싱글톤 service + store 분기"
```

---

## Task 9: 라우터 엔드포인트 + 예외→HTTP 매핑

**Files:**
- Modify: `backend/api/routers/management.py`
- Test: `backend/tests/management/test_regeneration_job_http_errors.py`

엔드포인트: `POST /regenerate/jobs`(start) · `GET /regenerate/jobs/{id}`(get) · `POST /regenerate/jobs/{id}/select`. 모두 `get_current_user` + org 해석으로 tenant를 강제한다. 예외→HTTP 매핑은 순수 함수로 분리해 단위 테스트한다.

- [ ] **Step 1: 실패 테스트 작성 (예외 매핑 함수)**

`backend/tests/management/test_regeneration_job_http_errors.py`:

```python
# 🅱 재생성 job 예외 → HTTPException 매핑 (라우터 단위)
import pytest
from fastapi import HTTPException

from api.routers.management import _job_http_error
from domain.management.execution.regeneration_jobs import (
    CandidateNotInJob,
    JobNotAwaitingSelection,
    JobNotFound,
    JobTenantMismatch,
    SelectionContextExpired,
)


@pytest.mark.parametrize(
    "exc,status",
    [
        (JobNotFound("j"), 404),
        (JobTenantMismatch("j"), 404),
        (JobNotAwaitingSelection("j"), 409),
        (SelectionContextExpired("j"), 409),
        (CandidateNotInJob("c"), 422),
    ],
)
def test_job_http_error_maps_status(exc, status):
    result = _job_http_error(exc)
    assert isinstance(result, HTTPException)
    assert result.status_code == status


def test_selection_expired_carries_reason_code():
    result = _job_http_error(SelectionContextExpired("j"))
    assert result.detail["reason"] == "SELECTION_CONTEXT_EXPIRED"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_regeneration_job_http_errors.py -v`
Expected: FAIL — `ImportError: cannot import name '_job_http_error'`

- [ ] **Step 3a: 매핑 함수 + import 추가**

`backend/api/routers/management.py` 상단 import 영역에 추가:

```python
from domain.management.execution.assistant_tools import execution_history
from domain.management.execution.regeneration_jobs import (
    CandidateNotInJob,
    JobNotAwaitingSelection,
    JobNotFound,
    JobTenantMismatch,
    SelectionContextExpired,
)
from domain.management.wiring import build_regeneration_job_service
```

`get_audit` 엔드포인트 근처(파일 내 적당한 위치)에 매핑 함수 추가:

```python
def _job_http_error(exc: Exception) -> HTTPException:
    """재생성 job 도메인 예외 → HTTPException. 라우터 분기 단일화."""
    if isinstance(exc, (JobNotFound, JobTenantMismatch)):
        return HTTPException(404, "job을 찾을 수 없습니다.")
    if isinstance(exc, CandidateNotInJob):
        return HTTPException(422, "선택한 후보가 이 job에 없습니다.")
    if isinstance(exc, SelectionContextExpired):
        return HTTPException(409, {"reason": "SELECTION_CONTEXT_EXPIRED"})
    if isinstance(exc, JobNotAwaitingSelection):
        return HTTPException(409, "선택 가능한 상태가 아닙니다.")
    return HTTPException(500, "알 수 없는 오류")
```

- [ ] **Step 3b: 엔드포인트 추가**

`management.py`에 엔드포인트 추가(요청 모델은 기존 `RegenerateRequest`의 `body.diagnosis` 패턴 재사용 — 컨텍스트는 `/regenerate`와 동일한 데모 값으로 구성). `_resolve_org_id`(파일 내 기존 함수)로 tenant 강제:

```python
class StartRegenJobRequest(BaseModel):
    diagnosis: DiagnosisResult


class SelectRegenJobRequest(BaseModel):
    selected_id: str


@router.post("/regenerate/jobs")
async def start_regen_job(
    body: StartRegenJobRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """재생성 비동기 job 시작 → {job_id, status}. 무거운 생성은 백그라운드."""
    org_id = await _resolve_org_id(user, db)
    if body.diagnosis.tenant_id != str(org_id):
        raise HTTPException(403, "다른 조직의 진단으로는 재생성할 수 없습니다.")
    context = RemediationContext(
        ad_account_id="act_demo_001",
        target_object_ids=(body.diagnosis.campaign_id,),
        budget_before_krw=DAILY_BUDGET_KRW,
        budget_after_krw=int(DAILY_BUDGET_KRW * 1.5),
        run_days=7,
        expected_state_version="state_v1",
        approval_policy_version=APPROVAL_POLICY_VERSION,
        action_type="REPLACE_CREATIVE",
    )
    service = build_regeneration_job_service(settings)
    job_id = await service.start(body.diagnosis, context)
    return {"job_id": job_id, "status": "queued"}


@router.get("/regenerate/jobs/{job_id}")
async def get_regen_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _resolve_org_id(user, db)
    service = build_regeneration_job_service(settings)
    try:
        rec = await service.get(job_id, tenant_id=str(org_id))
    except (JobNotFound, JobTenantMismatch) as exc:
        raise _job_http_error(exc) from exc
    return {
        "job_id": rec.id,
        "status": rec.status.value,
        "candidates": rec.candidates,
        "proposal": rec.proposal,
        "outcome_reason": rec.outcome_reason,
    }


@router.post("/regenerate/jobs/{job_id}/select")
async def select_regen_job(
    job_id: str,
    body: SelectRegenJobRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _resolve_org_id(user, db)
    service = build_regeneration_job_service(settings)
    try:
        rec = await service.select(job_id, body.selected_id, tenant_id=str(org_id))
    except (
        JobNotFound,
        JobTenantMismatch,
        JobNotAwaitingSelection,
        CandidateNotInJob,
        SelectionContextExpired,
    ) as exc:
        raise _job_http_error(exc) from exc
    return {"job_id": rec.id, "status": rec.status.value, "proposal": rec.proposal}


@router.get("/execution/history")
async def execution_history_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """테넌트의 최근 실행 감사 이력(읽기) — org 스코프 강제."""
    org_id = await _resolve_org_id(user, db)
    return await execution_history(_AUDIT_LOG, tenant_id=str(org_id))
```

- [ ] **Step 4: 통과 확인 + 라우터 import 무결성**

Run: `cd backend && uv run pytest tests/management/test_regeneration_job_http_errors.py -v`
Expected: PASS (6 passed)

Run: `cd backend && uv run python -c "import api.routers.management"`
Expected: 출력 없음(에러 없이 import). DiagnosisResult·User·_resolve_org_id 등이 미정의면 여기서 드러난다.

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format api/routers/management.py tests/management/test_regeneration_job_http_errors.py && uv run ruff check api/routers/management.py tests/management/test_regeneration_job_http_errors.py --fix
git add api/routers/management.py tests/management/test_regeneration_job_http_errors.py
git commit -m "add: 재생성 job 라우터(start/get/select)+execution/history+예외 매핑"
```

---

## Task 10: 전체 회귀 + import-linter 경계 확인

**Files:** 없음(검증만)

- [ ] **Step 1: 매니지먼트 전체 테스트**

Run: `cd backend && uv run pytest tests/management/ -v`
Expected: 전부 PASS (기존 + 신규).

- [ ] **Step 2: import 경계 확인**

Run: `cd backend && uv run lint-imports` (또는 CI와 동일한 import-linter 명령 — `pyproject.toml`/`.importlinter` 확인)
Expected: 경계 위반 없음. 특히 `execution/`이 `detection/` 또는 `approval`을 import하지 않아야 한다(설계 §1 — job 서비스는 DiagnosisResult만 contracts로 받는다).

- [ ] **Step 3: Ruff 최종**

Run: `cd backend && uv run ruff format . && uv run ruff check . --fix`
Expected: clean.

- [ ] **Step 4: 커밋(변경 있으면)**

```bash
cd backend && git add -A && git commit -m "edit: 재생성 job 핸드오프 Ruff/경계 정리" || echo "변경 없음"
```

---

## 소유권 핸드오프(코드 아님 — 합의 항목)

이 계획은 🅱 소유 + 🤝 공동까지만 구현한다. 다음은 **🅰 합의 후** 별도로 진행(설계 §5.1):
- `assistant/graph.py`·`tools.py`에 `start_regeneration`·`check_regeneration`·`execution_history`를 `@tool`로 등록 + 시스템 프롬프트 가드("개선/재생성 의도 명확할 때만 start_regeneration"). 툴 바디는 본 계획의 `execution/assistant_tools.py` 함수를 그대로 호출.
- `regeneration_jobs` 테이블 컬럼·`down_revision` 최종 합의(🤝).

---

## Self-Review 결과

- **Spec 커버리지**: §2 테이블/서비스/라이프사이클 → Task 1·2·3·4·7·8. §2.5 select 멱등·검증·_pending → Task 4. §3 tool-body → Task 6(등록은 핸드오프). §4.2 execution_history → Task 5·6·9. §5.2 테스트 6종 → Task 1·2·4·6·9 전반. §5.1 소유권 → 핸드오프 절. **interrupt 재개 비활성·SSE 제외·운영 큐 제외(§5.3)** 는 구현하지 않음으로 충족.
- **Placeholder 스캔**: 모든 코드 스텝에 실제 코드 포함, TBD 없음.
- **타입 일관성**: `RegenerationJobRecord`·`JobStatus`·`RegenerationJobStore`·`RegenerationJobService(start/run_job/get/select)`·`_job_http_error`·`execution_history`·`build_regeneration_job_service` 명칭이 정의 태스크와 사용 태스크에서 일치. `OutcomeKind`/`OutcomeReason`은 기존 `agents/outcome.py` 사용.
- **주의(구현자 확인)**: Task 9의 `_resolve_org_id`는 `User` 인자를 받는 기존 함수(`management.py:804`) — 시그니처가 다르면 해당 호출에 맞춰 인자만 조정. `lint-imports` 명령은 레포 설정에 맞춰 확인.
