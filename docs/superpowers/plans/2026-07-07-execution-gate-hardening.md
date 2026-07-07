# 집행 게이트 하드닝 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 승인 플레인의 보안 구멍 3개(무인증 /approve·approver_id 클라이언트 수신·승인 원장 부재)를 닫고, 집행 권장 게이트를 settings 정본으로 복원하고, launch_suggest(집행 제안) 루프를 연결한다.

**Architecture:** 스펙 `docs/superpowers/specs/2026-07-07-execution-gate-hardening-design.md` 기준. 기존 `IdempotencyKeyRow`/`AuditEventRow` + `db_stores.py` + `wiring.py` 교체 패턴을 그대로 따라 승인 원장(`ApprovalRecordRow` + `ApprovalStore` 포트)을 추가한다. executor의 `_validate()`는 sync 순수 함수로 유지하고, `execute()` 초반에 별도 async 원장 게이트(#5)를 호출한다. 게이트 임계값 정본은 `contracts/policy.py`(순수 함수) + `core/config.py`(settings)이며 시뮬 도메인·프론트가 이를 재사용한다.

**Tech Stack:** FastAPI + SQLAlchemy(async, NeonDB) + Alembic + pytest(asyncio_mode=auto) / Next.js(TS).

**실행 규칙**

- 백엔드 테스트: `cd backend && uv run pytest ../test/backend/<파일> -v` (testpaths·pythonpath는 backend/pyproject.toml에 설정됨 — 테스트는 저장소 루트 `test/backend/`에 있음).
- 각 태스크의 백엔드 커밋 전: `cd backend && uv run ruff format . && uv run ruff check . --fix`.
- 프론트 검증: `cd frontend && pnpm lint`.
- **Task 1은 core/models.py 공통부 변경 — 머지 전 팀 사전 공지 필수(협업 규칙). Task 9는 시뮬 도메인 파일 수정 — 시뮬팀 확인 전 머지 보류.**

---

### Task 1: 승인 원장 테이블 — `ApprovalRecordRow` + Alembic 0010

**Files:**
- Modify: `backend/core/models.py` (IdempotencyKeyRow 클래스 바로 아래, ~711행)
- Create: `backend/alembic/versions/0010_management_approval_records.py`

- [ ] **Step 1: ORM 모델 추가**

`backend/core/models.py`의 `IdempotencyKeyRow` 클래스(701~710행) 바로 아래에 추가한다. `_TS`, `String`, `Integer`, `Boolean`, `func`, `Mapped`, `mapped_column`은 이미 임포트되어 있다.

```python
class ApprovalRecordRow(Base):
    """승인 원장 (집행 게이트 #5) — 서버가 발행한 승인만 집행되게 하는 진위 대조 원본."""

    __tablename__ = "management_approval_records"

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(64), index=True)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    approver_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_tier: Mapped[int] = mapped_column(Integer, nullable=False)  # ActionTier(IntEnum) 값
    execution_mode: Mapped[str] = mapped_column(String(16), nullable=False)  # ExecutionMode.value
    approval_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_state_version: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(_TS, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(_TS, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(_TS)  # 집행 성공 시 마킹
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
```

- [ ] **Step 2: Alembic 마이그레이션 작성**

`backend/alembic/versions/0010_management_approval_records.py` 신규 생성 (0009 패턴 — raw SQL + IF NOT EXISTS 멱등 가드):

```python
# 승인 원장 테이블(management_approval_records) 신설 — 집행 게이트 #5(승인 위조 방지)
"""add management_approval_records table + indexes

Revision ID: 0010_management_approval_records
Revises: 0009_center_suggestions
Create Date: 2026-07-07

스펙: docs/superpowers/specs/2026-07-07-execution-gate-hardening-design.md §3.3.
서버가 발행한 ApprovedAction의 스냅샷 원장 — executor가 /execute 제출본과 대조해
위조(원장 부재·필드 불일치, 특히 execution_mode LIVE 바꿔치기)를 차단한다.
빈 DB는 0001_baseline의 create_all이 ORM(ApprovalRecordRow)대로 바로 만들고,
아래 멱등 가드(IF NOT EXISTS)가 no-op이 된다. 재실행 안전.
"""

from alembic import op

revision = "0010_management_approval_records"
down_revision = "0009_center_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS management_approval_records (
            approval_id VARCHAR(64) PRIMARY KEY,
            proposal_id VARCHAR(64) NOT NULL,
            proposal_hash VARCHAR(64) NOT NULL,
            tenant_id VARCHAR(64) NOT NULL,
            approver_id VARCHAR(64) NOT NULL,
            action_tier INTEGER NOT NULL,
            execution_mode VARCHAR(16) NOT NULL,
            approval_policy_version VARCHAR(64) NOT NULL,
            expected_state_version VARCHAR(64) NOT NULL,
            approved_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mgmt_approval_proposal "
        "ON management_approval_records (proposal_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mgmt_approval_tenant "
        "ON management_approval_records (tenant_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS management_approval_records")
```

- [ ] **Step 3: 임포트 스모크 확인**

Run: `cd backend && uv run python -c "from core.models import ApprovalRecordRow; print(ApprovalRecordRow.__tablename__)"`
Expected: `management_approval_records`

- [ ] **Step 4: (dev DB 연결 가능 시) 마이그레이션 적용**

Run: `cd backend && uv run alembic upgrade head`
Expected: `0009_center_suggestions -> 0010_management_approval_records` 로그. DB 연결 불가 환경이면 이 스텝은 건너뛰고 커밋 메시지에 "마이그레이션 미적용" 명시.

- [ ] **Step 5: Ruff + 커밋 (⚠️ 공통부 — 팀 사전 공지 후 머지)**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/core/models.py backend/alembic/versions/0010_management_approval_records.py
git commit -m "add: 승인 원장 테이블(management_approval_records) + Alembic 0010 — 집행 게이트 #5 기반"
```

---

### Task 2: 승인 원장 계약·저장소 — 포트 / 인메모리 / DB / wiring

**Files:**
- Create: `backend/domain/management/contracts/approval_ledger.py`
- Create: `backend/domain/management/execution/approval_stores.py`
- Modify: `backend/domain/management/execution/db_stores.py` (파일 끝에 추가)
- Modify: `backend/domain/management/wiring.py` (build_audit_sink 아래에 추가)
- Test: `test/backend/management/test_approval_ledger.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/management/test_approval_ledger.py` 신규 생성:

```python
# 승인 원장 — 레코드 생성/대조·인메모리 저장소·DB row 변환 (집행 게이트 #5 기반)
from domain.management.contracts.approval_ledger import (
    record_from_action,
    record_mismatches,
)
from domain.management.contracts.enums import ExecutionMode
from domain.management.execution.approval_stores import InMemoryApprovalStore
from management.helpers import NOW, make_action, make_proposal


def test_record_from_action_mirrors_fields_and_matches():
    proposal = make_proposal()
    action = make_action(proposal)
    record = record_from_action(action)
    assert record.approval_id == action.approval_id
    assert record.consumed_at is None
    assert record_mismatches(record, action) == []


def test_record_mismatches_detects_execution_mode_swap():
    proposal = make_proposal()
    action = make_action(proposal)  # execution_mode=MOCK으로 발행
    record = record_from_action(action)
    forged = action.model_copy(update={"execution_mode": ExecutionMode.LIVE})
    assert "execution_mode" in record_mismatches(record, forged)


def test_record_mismatches_detects_approver_swap():
    proposal = make_proposal()
    action = make_action(proposal)
    record = record_from_action(action)
    forged = action.model_copy(update={"approver_id": "attacker-1"})
    assert record_mismatches(record, forged) == ["approver_id"]


async def test_inmemory_store_put_get_consume():
    proposal = make_proposal()
    action = make_action(proposal)
    store = InMemoryApprovalStore()
    assert await store.get(action.approval_id) is None
    await store.put(record_from_action(action))
    got = await store.get(action.approval_id)
    assert got is not None and got.approval_id == action.approval_id
    await store.consume(action.approval_id, NOW)
    consumed = await store.get(action.approval_id)
    assert consumed is not None and consumed.consumed_at == NOW


def test_db_row_roundtrip():
    from domain.management.execution.db_stores import approval_record_to_row, row_to_approval_record

    proposal = make_proposal()
    record = record_from_action(make_action(proposal))
    row = approval_record_to_row(record)
    assert row.action_tier == int(record.action_tier)
    assert row.execution_mode == record.execution_mode.value
    back = row_to_approval_record(row)
    assert back == record
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_approval_ledger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.management.contracts.approval_ledger'`

- [ ] **Step 3: 계약 구현 — `contracts/approval_ledger.py`**

```python
# 승인 원장 계약 — 서버 발행 승인의 진위 대조(집행 게이트 #5) 레코드·포트
"""승인 원장 계약 — 서버 발행 승인의 진위 대조(집행 게이트 #5) 레코드·포트.

발행부(approval.issue_approval)와 검증부(executor)가 이 계약만 공유한다.
저장소 구현은 execution/approval_stores.py(인메모리)·execution/db_stores.py(DB),
교체는 wiring.build_approval_store에서만.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, Protocol

from domain.management.contracts.enums import ActionTier, ExecutionMode
from domain.management.contracts.schemas import ApprovedAction, Contract, UtcDatetime


class ApprovalRecord(Contract):
    """발행 시점 ApprovedAction 스냅샷 + 소진 시각 — 원장의 1행."""

    approval_id: str
    proposal_id: str
    proposal_hash: str
    tenant_id: str
    approver_id: str
    action_tier: ActionTier
    execution_mode: ExecutionMode
    approval_policy_version: str
    expected_state_version: str
    approved_at: UtcDatetime
    expires_at: UtcDatetime
    consumed_at: UtcDatetime | None = None


#: 제출된 ApprovedAction과 원장을 대조하는 필드 — 스펙 §3.3(9필드).
#: execution_mode는 위조 시 LIVE 전환 위험이라 반드시 포함.
VERIFIED_FIELDS: Final[tuple[str, ...]] = (
    "proposal_id",
    "proposal_hash",
    "tenant_id",
    "approver_id",
    "action_tier",
    "execution_mode",
    "approval_policy_version",
    "expected_state_version",
    "expires_at",
)


def record_from_action(action: ApprovedAction) -> ApprovalRecord:
    """발행 직후 스냅샷 — 원장에 남길 레코드."""
    return ApprovalRecord(
        approval_id=action.approval_id,
        proposal_id=action.proposal_id,
        proposal_hash=action.proposal_hash,
        tenant_id=action.tenant_id,
        approver_id=action.approver_id,
        action_tier=action.action_tier,
        execution_mode=action.execution_mode,
        approval_policy_version=action.approval_policy_version,
        expected_state_version=action.expected_state_version,
        approved_at=action.approved_at,
        expires_at=action.expires_at,
    )


def record_mismatches(record: ApprovalRecord, action: ApprovedAction) -> list[str]:
    """불일치 필드명 목록 — 빈 리스트면 진본."""
    return [f for f in VERIFIED_FIELDS if getattr(record, f) != getattr(action, f)]


class ApprovalStore(Protocol):
    """승인 원장 저장소 포트 — 발행부와 executor가 같은 인스턴스를 공유해야 한다."""

    async def put(self, record: ApprovalRecord) -> None: ...

    async def get(self, approval_id: str) -> ApprovalRecord | None: ...

    async def consume(self, approval_id: str, at: datetime) -> None: ...
```

- [ ] **Step 4: 인메모리 저장소 — `execution/approval_stores.py`**

```python
# 승인 원장 인메모리 저장소 — use_mock·테스트용 (DB 구현은 db_stores.DbApprovalStore)
"""승인 원장 인메모리 저장소 — use_mock·테스트용 (DB 구현은 db_stores.DbApprovalStore)."""

from __future__ import annotations

from datetime import datetime

from domain.management.contracts.approval_ledger import ApprovalRecord


class InMemoryApprovalStore:
    """dict 기반 — Contract는 frozen이라 consume은 사본 교체로 마킹한다."""

    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}

    async def put(self, record: ApprovalRecord) -> None:
        self._records[record.approval_id] = record

    async def get(self, approval_id: str) -> ApprovalRecord | None:
        return self._records.get(approval_id)

    async def consume(self, approval_id: str, at: datetime) -> None:
        rec = self._records.get(approval_id)
        if rec is not None and rec.consumed_at is None:
            self._records[approval_id] = rec.model_copy(update={"consumed_at": at})
```

- [ ] **Step 5: DB 저장소 — `execution/db_stores.py` 파일 끝에 추가**

임포트 블록에 추가: `from core.models import ApprovalRecordRow, AuditEventRow, IdempotencyKeyRow` (기존 라인 확장), `from domain.management.contracts.approval_ledger import ApprovalRecord`, `from domain.management.contracts.enums import ActionTier, ExecutionMode`, `from datetime import datetime`.

```python
def approval_record_to_row(record: ApprovalRecord) -> ApprovalRecordRow:
    """계약 → ORM row. enum은 int/str 값으로 저장."""
    return ApprovalRecordRow(
        approval_id=record.approval_id,
        proposal_id=record.proposal_id,
        proposal_hash=record.proposal_hash,
        tenant_id=record.tenant_id,
        approver_id=record.approver_id,
        action_tier=int(record.action_tier),
        execution_mode=record.execution_mode.value,
        approval_policy_version=record.approval_policy_version,
        expected_state_version=record.expected_state_version,
        approved_at=record.approved_at,
        expires_at=record.expires_at,
        consumed_at=record.consumed_at,
    )


def row_to_approval_record(row: ApprovalRecordRow) -> ApprovalRecord:
    return ApprovalRecord(
        approval_id=row.approval_id,
        proposal_id=row.proposal_id,
        proposal_hash=row.proposal_hash,
        tenant_id=row.tenant_id,
        approver_id=row.approver_id,
        action_tier=ActionTier(row.action_tier),
        execution_mode=ExecutionMode(row.execution_mode),
        approval_policy_version=row.approval_policy_version,
        expected_state_version=row.expected_state_version,
        approved_at=row.approved_at,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
    )


class DbApprovalStore:
    """management_approval_records 기반 승인 원장 (집행 게이트 #5)."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal
    ) -> None:
        self._sf = session_factory

    async def put(self, record: ApprovalRecord) -> None:
        async with self._sf() as session:
            session.add(approval_record_to_row(record))
            await session.commit()

    async def get(self, approval_id: str) -> ApprovalRecord | None:
        async with self._sf() as session:
            row = await session.get(ApprovalRecordRow, approval_id)
        return None if row is None else row_to_approval_record(row)

    async def consume(self, approval_id: str, at: datetime) -> None:
        async with self._sf() as session:
            row = await session.get(ApprovalRecordRow, approval_id)
            if row is not None and row.consumed_at is None:
                row.consumed_at = at
                await session.commit()
```

- [ ] **Step 6: wiring — `build_approval_store` 싱글턴 추가**

`backend/domain/management/wiring.py`의 `build_audit_sink` 함수 아래에 추가. TYPE_CHECKING 블록에 `from domain.management.contracts.approval_ledger import ApprovalStore` 추가.

```python
_approval_store: ApprovalStore | None = None


def build_approval_store(settings) -> ApprovalStore:
    """승인 원장 — 발행부(라우터)와 executor가 같은 인스턴스를 봐야 하므로 싱글턴.

    use_mock이면 인메모리, 아니면 DB(management_approval_records).
    """
    global _approval_store  # noqa: PLW0603
    if _approval_store is None:
        if getattr(settings, "use_mock", True):
            from domain.management.execution.approval_stores import (  # noqa: PLC0415
                InMemoryApprovalStore,
            )

            _approval_store = InMemoryApprovalStore()
        else:
            from domain.management.execution.db_stores import DbApprovalStore  # noqa: PLC0415

            _approval_store = DbApprovalStore()
    return _approval_store
```

주의: `_approval_store: ApprovalStore | None = None` 타입 표기는 런타임 평가되지 않게 문자열 없이 두려면 `from __future__ import annotations`가 이미 wiring.py 1행에 있는지 확인(있음, 3행). 문제 없으면 그대로.

- [ ] **Step 7: 테스트 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_approval_ledger.py -v`
Expected: 5 passed

- [ ] **Step 8: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/contracts/approval_ledger.py backend/domain/management/execution/approval_stores.py backend/domain/management/execution/db_stores.py backend/domain/management/wiring.py test/backend/management/test_approval_ledger.py
git commit -m "add: 승인 원장 계약(ApprovalRecord·ApprovalStore)·저장소(인메모리/DB)·wiring 싱글턴"
```

---

### Task 3: 승인 발행 + 원장 기록 — `issue_approval()`

**Files:**
- Modify: `backend/domain/management/approval.py`
- Test: `test/backend/management/test_approval_ledger.py` (테스트 추가)

- [ ] **Step 1: 실패하는 테스트 추가**

`test/backend/management/test_approval_ledger.py` 끝에 추가:

```python
async def test_issue_approval_writes_ledger_record():
    from domain.management.approval import issue_approval
    from domain.management.contracts.policy import APPROVAL_POLICY_VERSION

    proposal = _fresh_valid_proposal()
    store = InMemoryApprovalStore()
    action = await issue_approval(
        proposal, "user-77", execution_mode=ExecutionMode.MOCK, store=store
    )
    assert action.approver_id == "user-77"
    record = await store.get(action.approval_id)
    assert record is not None
    assert record_mismatches(record, action) == []


async def test_issue_approval_rejects_invalid_proposal():
    # 유일한 발행 진입점 — 만료·해시·정책버전 검증을 여기서 강제한다(내부 경로 포함).
    import pytest

    from domain.management.approval import ApprovalIssueError, issue_approval

    proposal = make_proposal()  # helpers.NOW(과거) 기준 — 실시간 검증에서 만료
    store = InMemoryApprovalStore()
    with pytest.raises(ApprovalIssueError) as exc:
        await issue_approval(proposal, "user-77", execution_mode=ExecutionMode.MOCK, store=store)
    assert exc.value.issues  # 사유 목록 보존 — 라우터가 409 detail로 변환
    assert store._records == {}  # 발행 실패 시 원장에 아무것도 남지 않는다
```

파일 상단에 헬퍼 추가(임포트 아래 — 첫 테스트 `test_issue_approval_writes_ledger_record`가 사용):

```python
from datetime import UTC, datetime, timedelta

from domain.management.contracts.policy import APPROVAL_POLICY_VERSION


def _fresh_valid_proposal():
    """실시간 3단계 검증(만료·해시·정책버전)을 통과하는 제안."""
    now = datetime.now(UTC)
    return make_proposal(
        approval_policy_version=APPROVAL_POLICY_VERSION,
        metrics_as_of=now,
        expires_at=now + timedelta(hours=1),
    )
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_approval_ledger.py -v`
Expected: FAIL — `ImportError: cannot import name 'issue_approval'`

- [ ] **Step 3: 구현**

`backend/domain/management/approval.py` — 임포트 블록에 추가:

```python
from domain.management.contracts.approval_ledger import ApprovalStore, record_from_action
```

파일 끝(`approve` 함수 아래)에 추가:

```python
class ApprovalIssueError(ValueError):
    """발행 전 검증 실패 — issues에 사유 목록 보존(라우터가 409 detail로 변환)."""

    def __init__(self, issues: list[str]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


async def issue_approval(
    proposal: ActionProposal,
    approver_id: str,
    *,
    execution_mode: ExecutionMode = ExecutionMode.MOCK,
    store: ApprovalStore,
) -> ApprovedAction:
    """검증 + 승인 발행 + 원장 기록 — 집행 가능한 승인의 유일한 발행 진입점 (게이트 #5).

    3단계 검증(만료·해시·정책버전)을 여기서 강제한다 — /approve뿐 아니라
    activate·pause·budget-commit 등 내부 발행 경로도 같은 관문을 거친다.
    원장에 없는 승인은 executor가 위조로 거부하므로, 모든 발행 경로는
    approve() 직접 호출 대신 이 함수를 거쳐야 한다.
    """
    issues = validate_proposal(proposal)
    if issues:
        raise ApprovalIssueError(issues)
    action = approve(proposal, approver_id, execution_mode=execution_mode)
    await store.put(record_from_action(action))
    return action
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_approval_ledger.py -v`
Expected: 6 passed

- [ ] **Step 5: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/approval.py test/backend/management/test_approval_ledger.py
git commit -m "add: 승인 발행+원장 기록 issue_approval — 발행 단일 진입점"
```

---

### Task 4: executor 원장 게이트(#5) — 위조 승인 차단 + 소진 마킹

**Files:**
- Modify: `backend/domain/management/execution/executor.py`
- Modify: `test/backend/management/helpers.py` (build_executor에 approvals 파라미터)
- Test: `test/backend/management/test_approval_ledger_gate.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/management/test_approval_ledger_gate.py` 신규 생성:

```python
# executor 승인 원장 게이트(#5) — 위조 차단·필드 대조·소진 마킹·명시적 생략
from domain.management.contracts.approval_ledger import record_from_action
from domain.management.contracts.enums import ExecutionMode, FailureReason, ResultStatus
from domain.management.execution.approval_stores import InMemoryApprovalStore
from domain.management.execution.audit_log import InMemoryAuditLog
from domain.management.execution.executor import Executor, InMemoryIdempotencyStore
from domain.management.execution.tier import BudgetAuthority
from management.helpers import (
    NOW,
    POLICY_VERSION,
    STATE_VERSION,
    FakeWriter,
    build_executor,
    make_action,
    make_proposal,
)


async def test_forged_action_without_ledger_record_rejected():
    approvals = InMemoryApprovalStore()
    executor, *_ = build_executor(FakeWriter(), approvals=approvals)
    proposal = make_proposal()
    forged = make_action(proposal)  # 원장에 put하지 않음 = 서버 발행 아님
    result = await executor.execute(forged, proposal)
    assert result.status is not ResultStatus.SUCCESS
    assert result.failure_reason is FailureReason.UNAPPROVED_ACTION


async def test_execution_mode_swap_rejected():
    approvals = InMemoryApprovalStore()
    executor, *_ = build_executor(FakeWriter(), approvals=approvals)
    proposal = make_proposal()
    action = make_action(proposal)  # MOCK으로 발행·기록
    await approvals.put(record_from_action(action))
    swapped = action.model_copy(update={"execution_mode": ExecutionMode.DRY_RUN})
    result = await executor.execute(swapped, proposal)
    assert result.status is not ResultStatus.SUCCESS
    assert result.failure_reason is FailureReason.UNAPPROVED_ACTION


async def test_genuine_action_executes_and_marks_consumed():
    approvals = InMemoryApprovalStore()
    executor, *_ = build_executor(FakeWriter(), approvals=approvals)
    proposal = make_proposal()
    action = make_action(proposal)
    await approvals.put(record_from_action(action))
    result = await executor.execute(action, proposal)
    assert result.status is ResultStatus.SUCCESS
    record = await approvals.get(action.approval_id)
    assert record is not None and record.consumed_at is not None


async def test_gate_skipped_only_by_explicit_none():
    # 게이트 생략은 기본값이 아니라 명시적 결정 — helper를 거치지 않고 Executor를 직접
    # 생성해 approvals=None이 호출부에 드러나는 형태(필수 키워드 인자)를 검증한다.
    async def _state(_ad_account_id: str) -> str:
        return STATE_VERSION

    async def _no_sleep(_s: float) -> None:
        return None

    budget = BudgetAuthority(limit_krw=1_000_000)
    executor = Executor(
        FakeWriter(),
        idempotency=InMemoryIdempotencyStore(),
        audit=InMemoryAuditLog(),
        budget_for=lambda _tenant_id: budget,
        state_version_provider=_state,
        current_policy_version=POLICY_VERSION,
        clock=lambda: NOW,
        sleep=_no_sleep,
        approvals=None,  # 의도적 생략 — 데모 CLI 등 라우터 미경유 경로 전용
    )
    proposal = make_proposal()
    action = make_action(proposal)
    result = await executor.execute(action, proposal)
    assert result.status is ResultStatus.SUCCESS
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_approval_ledger_gate.py -v`
Expected: FAIL — `build_executor() got an unexpected keyword argument 'approvals'`

- [ ] **Step 3: 테스트 헬퍼 수정 — `test/backend/management/helpers.py`**

`build_executor` 시그니처와 Executor 호출에 `approvals` 전달 추가 (229~255행):

```python
def build_executor(
    writer: FakeWriter,
    *,
    limit_krw: int = 1_000_000,
    state_version: str = STATE_VERSION,
    policy: str = POLICY_VERSION,
    now: datetime = NOW,
    approvals=None,  # 승인 원장(게이트 #5) — None이면 게이트 생략(기존 테스트 호환)
):
    """executor + 인메모리 의존성 일괄 조립. (executor, audit, idem, budget) 반환."""

    async def state_provider(_ad_account_id: str) -> str:
        return state_version

    audit = InMemoryAuditLog()
    idem = InMemoryIdempotencyStore()
    budget = BudgetAuthority(limit_krw=limit_krw)
    executor = Executor(
        writer,
        idempotency=idem,
        audit=audit,
        budget_for=lambda _tenant_id: budget,
        state_version_provider=state_provider,
        current_policy_version=policy,
        clock=lambda: now,
        sleep=_no_sleep,
        approvals=approvals,
    )
    return executor, audit, idem, budget
```

- [ ] **Step 4: Executor 구현 — `backend/domain/management/execution/executor.py`**

(a) 임포트 블록에 추가:

```python
from domain.management.contracts.approval_ledger import ApprovalStore, record_mismatches
```

(b) `__init__` 시그니처(122~138행)에 파라미터 추가 — `history_recorder` 라인 뒤. **기본값 없음(필수 키워드)** — 조용히 게이트가 꺼지는 것을 막는다. 게이트를 의도적으로 끄려면 호출부가 `approvals=None`을 명시적으로 써야 하고, 그 결정이 코드리뷰에 드러난다:

```python
        history_recorder: HistoryRecorder | None = None,  # None=기록 생략(테스트·미배선)
        # 승인 원장(게이트 #5) — 기본값 없음(필수). None은 의도적 생략 명시(데모 CLI 등).
        approvals: ApprovalStore | None,
```

본문에 저장 추가(`self._history_recorder = history_recorder` 근처):

```python
        self._approvals = approvals
```

(c) `execute()`의 sync `_validate` 직후(157~160행 `rejection` 블록 바로 아래, `# 5) expected_state_version` 주석 위)에 원장 게이트 삽입:

```python
        # 4.5) 승인 원장 대조 (게이트 #5) — 서버가 발행하지 않은(위조) 승인 차단.
        # _validate()는 sync 순수 함수로 유지하고 원장 조회(async)만 여기서 한다(스펙 §3.3).
        ledger_rejection = await self._verify_approval_record(action)
        if ledger_rejection is not None:
            reason, detail = ledger_rejection
            return await self._reject(run, action, proposal, reason, detail)
```

(d) `_validate` 메서드 위(261행 `# ── 4)단계 검증` 주석 아래)에 메서드 추가:

```python
    async def _verify_approval_record(
        self, action: ApprovedAction
    ) -> tuple[FailureReason, str] | None:
        """게이트 #5 — 제출된 ApprovedAction을 서버 승인 원장과 대조한다."""
        if self._approvals is None:
            return None
        record = await self._approvals.get(action.approval_id)
        if record is None:
            return FailureReason.UNAPPROVED_ACTION, "승인 원장에 없는 approval_id (게이트 #5)"
        mismatched = record_mismatches(record, action)
        if mismatched:
            return (
                FailureReason.UNAPPROVED_ACTION,
                f"승인 원장 불일치: {', '.join(mismatched)} (게이트 #5)",
            )
        return None
```

(e) 성공 시 소진 마킹 — `execute()`의 성공 분기(224~226행 `await self._idempotency.save_result(key, result)` / `budget.commit(...)` 직후)에 추가:

```python
            if self._approvals is not None:
                with contextlib.suppress(Exception):  # 마킹 실패가 실행 결과를 바꾸지 않게
                    await self._approvals.consume(action.approval_id, self._clock())
```

주의: 소진(consumed_at)은 관측·감사용 마킹이다. 재제출 차단은 기존 멱등 게이트가 담당하므로, `_verify_approval_record`는 consumed 여부로 거부하지 않는다(멱등 재생 경로가 깨지지 않게).

- [ ] **Step 4.5: 필수 인자화에 따른 기존 직접 생성부 갱신 (전수 2곳 — grep으로 재확인)**

`approvals`가 필수 키워드가 되면서 깨지는 `Executor(...)` 직접 생성부를 갱신한다. 확인 명령: `rg "Executor\(" backend test` — 계획 시점 전수: 라우터 2곳·wiring 1곳(Task 5에서 스토어 주입), 아래 2곳(명시적 None).

(a) `backend/scripts/management_demo.py:142` — `Executor(` 호출에 인자 추가:

```python
        approvals=None,  # 데모 CLI — 원장 게이트 의도적 생략(라우터 미경유·실지출 없음)
```

(b) `test/backend/management/test_history_recorder.py:29` — `Executor(` 호출에 인자 추가:

```python
        approvals=None,  # 원장 게이트 비대상 테스트 — 의도적 생략 명시
```

- [ ] **Step 5: 신규 + 기존 게이트 테스트 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_approval_ledger_gate.py ../test/backend/management/test_executor_gates.py ../test/backend/management/test_history_recorder.py -v`
Expected: 전부 PASS (기존 테스트는 helpers.build_executor의 `approvals=None` 기본값 경유 — 테스트 헬퍼에서만 기본값 허용)

- [ ] **Step 6: ⚠️ 이 태스크에서는 커밋하지 않는다 — Task 5와 한 커밋**

`approvals` 필수 인자화로 라우터 `_get_executor()`·wiring `build_executor()`가 TypeError 상태가 되므로, 이 시점의 management **전체** 스위트는 라우터 테스트에서 깨지는 게 정상이다(표적 테스트만 통과 확인). 반대로 라우터에 게이트만 먼저 배선하면 `/approve`가 아직 원장을 쓰지 않아 풀사이클 테스트가 원장 부재 거부로 깨진다. 따라서 **executor 게이트 + 라우터/wiring 배선 + /approve 재작성 + 발행 4곳 교체는 Task 5에서 단일 커밋**으로 묶는다 — 모든 커밋이 green이어야 한다는 원칙 유지.

---

### Task 5: 라우터 — /approve 인증·approver 서버 주입·발행 4곳 일원화 + 프론트 api.ts (Task 4와 단일 커밋)

**Files:**
- Modify: `backend/api/routers/management.py` (686~706행 /approve, 241~267행 _get_executor, 3093·3232·3415행 approve 호출 3곳, 임포트)
- Modify: `backend/domain/management/wiring.py` (build_executor에 approvals 주입)
- Modify: `frontend/src/lib/api.ts` (827~831행)
- Test: `test/backend/management/test_approve_endpoint.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/management/test_approve_endpoint.py` 신규 생성. 이 파일의 `_FakeDB`는 `test_authz_hardening.py`의 최소 복제(require_user_org가 `db.scalar`로 organization_members를 조회하는 것만 지원):

```python
# /approve 승인 플레인 폐쇄 — 무인증 401·org 검증·approver 서버 주입·원장 기록
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routers import management
from core.db import get_db
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION
from domain.management.execution.approval_stores import InMemoryApprovalStore
from management.helpers import make_proposal


class _FakeDB:
    def __init__(self, org_id=None):
        self._org_id = org_id

    async def scalar(self, stmt, *a, **k):
        if "organization_members" in str(stmt):
            return self._org_id
        return None


def _fresh_proposal(tenant_id: str):
    """실시간 검증(만료·정책버전)을 통과하는 제안 — helpers.NOW(과거)가 아닌 현재 기준."""
    now = datetime.now(UTC)
    return make_proposal(
        tenant_id=tenant_id,
        approval_policy_version=APPROVAL_POLICY_VERSION,
        metrics_as_of=now,
        expires_at=now + timedelta(hours=1),
    )


def test_approve_unauthenticated_401():
    """무인증 실 HTTP 요청 — get_current_user를 오버라이드하지 않고 401을 확인한다."""
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_db] = lambda: _FakeDB()  # auth는 실물, db만 지연 페이크
    client = TestClient(app)
    res = client.post("/api/management/approve", json={"proposal": {}, "approved": True})
    assert res.status_code == 401


def test_approval_request_has_no_approver_id_field():
    """approver_id는 서버 주입 — 요청 모델에서 필드 자체가 제거되고 extra는 무시된다."""
    proposal = _fresh_proposal("org-x")
    body = management.ApprovalRequest(proposal=proposal, approved=True, approver_id="attacker")
    assert not hasattr(body, "approver_id")


async def test_approve_cross_org_403(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", True, raising=False)
    org = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    proposal = _fresh_proposal("org-someone-else")
    body = management.ApprovalRequest(proposal=proposal, approved=True)
    with pytest.raises(HTTPException) as exc:
        await management.approve_proposal(body, user=user, db=_FakeDB(org_id=org))
    assert exc.value.status_code == 403


async def test_approve_injects_server_approver_and_writes_ledger(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", True, raising=False)
    store = InMemoryApprovalStore()
    monkeypatch.setattr(management, "_APPROVAL_STORE", store)
    org = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    proposal = _fresh_proposal(str(org))
    body = management.ApprovalRequest(proposal=proposal, approved=True)
    out = await management.approve_proposal(body, user=user, db=_FakeDB(org_id=org))
    action = out["approved_action"]
    assert action["approver_id"] == str(user.id)  # 서버 주입 — 클라이언트 지정 불가
    assert await store.get(action["approval_id"]) is not None  # 원장 기록됨


async def test_approve_demo_sentinel_allowed_for_any_org(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", True, raising=False)
    store = InMemoryApprovalStore()
    monkeypatch.setattr(management, "_APPROVAL_STORE", store)
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    proposal = _fresh_proposal(management.TENANT_ID)  # 시연 센티넬 — org 불일치 면제
    body = management.ApprovalRequest(proposal=proposal, approved=True)
    out = await management.approve_proposal(body, user=user, db=_FakeDB(org_id=uuid.uuid4()))
    assert out["status"] == "approved"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_approve_endpoint.py -v`
Expected: FAIL — 시그니처에 user/db 없음, ApprovalRequest에 approver_id 존재, `_APPROVAL_STORE` 속성 없음

- [ ] **Step 3: 라우터 구현 — `backend/api/routers/management.py`**

(a) 임포트 수정 — `from domain.management.approval import ...` 라인에 `ApprovalIssueError, issue_approval` 추가(기존 `approve`·`validate_proposal`은 라우터 내 다른 사용처가 없어지면 제거), wiring 임포트 라인에 `build_approval_store` 추가.

(b) 모듈 레벨(다른 wiring 싱글턴 `_AUDIT_LOG` 근처)에 원장 싱글턴 추가:

```python
_APPROVAL_STORE = build_approval_store(settings)  # 승인 원장 — 발행(/approve)과 executor가 공유
```

(c) `_get_executor()`(241~267행)의 **두 Executor(...) 호출 모두**에 인자 추가:

```python
            approvals=_APPROVAL_STORE,
```

(d) `/approve` 엔드포인트(686~706행) 교체:

```python
class ApprovalRequest(BaseModel):
    proposal: ActionProposal
    approved: bool


@router.post("/approve")
async def approve_proposal(
    body: ApprovalRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """승인 플레인 — 로그인 필수. 승인자는 서버가 주입(user.id), 발행은 원장 기록 동반.

    시연 제안(TENANT_ID 센티넬)은 /execute와 동일하게 org 일치 면제(로그인은 필수).
    """
    org_id = await _require_org_id_write(user, db, action="approve")
    if body.proposal.tenant_id != TENANT_ID and body.proposal.tenant_id != str(org_id):
        raise HTTPException(403, "다른 조직의 제안은 승인할 수 없습니다.")

    if not body.approved:
        return {
            "status": "rejected",
            "detail": "거절됨 — 무승인 액션은 어떤 경로로도 Writer에 도달 불가 (불변 규칙 #2)",
        }

    # 3단계 검증(만료·해시·정책버전)은 issue_approval 내부에서 강제된다(발행 단일 진입점).
    try:
        action = await issue_approval(
            body.proposal,
            str(user.id),
            execution_mode=_resolved_execution_mode(),
            store=_APPROVAL_STORE,
        )
    except ApprovalIssueError as exc:
        raise HTTPException(status_code=409, detail={"issues": exc.issues}) from exc
    return {"status": "approved", "approved_action": action.model_dump(mode="json")}
```

(e) 나머지 발행 3곳 교체 — 3093행(activate)·3232행(pause 부근)·3415행(budget-commit)의

```python
    action = approve(proposal, str(user.id), execution_mode=_resolved_execution_mode())
```

을 각각 다음으로 교체(3곳 모두 동일):

```python
    action = await issue_approval(
        proposal, str(user.id), execution_mode=_resolved_execution_mode(), store=_APPROVAL_STORE
    )
```

교체 후 `approve`가 라우터에서 더 이상 안 쓰이면 임포트에서 제거. **한 곳이라도 빠지면 그 경로의 집행이 원장 게이트에서 전부 거부되므로 3곳 전부 교체 필수.** 이 3곳의 제안은 서버가 방금 `finalize_proposal`로 만든 것이라 `issue_approval`의 검증을 항상 통과한다 — `ApprovalIssueError`가 새어 나오면(500) 제안 생성 코드의 버그 신호이므로 try/except를 두지 않는다(fail-fast).

- [ ] **Step 4: wiring build_executor에도 원장 주입 — `backend/domain/management/wiring.py`**

`build_executor()`(185~224행)의 `return Executor(...)` 호출에 인자 추가:

```python
        approvals=build_approval_store(settings),  # 승인 원장(게이트 #5) — 싱글턴 공유
```

- [ ] **Step 5: 프론트 — `frontend/src/lib/api.ts` 827~831행**

```typescript
    approve: (proposal: unknown, approved: boolean) =>
      request("/management/approve", {
        method: "POST",
        body: JSON.stringify({ proposal, approved }),  // approver_id는 서버가 주입
      }),
```

- [ ] **Step 6: 테스트 통과 + 회귀 확인 (영향 파일 명시 체크리스트)**

Run: `cd backend && uv run pytest ../test/backend/management/test_approve_endpoint.py -v`
Expected: 5 passed

기존 테스트 영향 전수(grep `approver_id|/approve` 기준) — 하나씩 확인:

- `test/backend/management/test_management_router.py` (111·133행): `/approve`에 `approver_id: "user_demo"`를 여전히 보냄 — 요청 모델이 extra를 무시하므로 **통과 예상**. 단 죽은 필드이므로 json에서 `approver_id` 키 제거로 정리. client 픽스처는 이미 get_current_user·get_db 오버라이드 + org=TENANT_ID(데모 센티넬)라 인증·org 검증 통과.
- `test/backend/management/test_create_proposal_router.py` (120행): approver_id 없이 호출 — 픽스처가 인증 오버라이드를 이미 하고 있고 proposal tenant가 픽스처 org와 일치하는지 확인. 불일치면 403이 새 정상 동작이므로 픽스처 org를 proposal tenant에 맞춘다.
- `test/backend/management/test_acceptance.py` (161행): `approve()` 도메인 함수 직접 사용 — `approve()`는 그대로 유지되므로 **영향 없음**.
- `test/backend/management/test_executor_gates.py`: `make_action` 직접 생성 + helpers `build_executor`(approvals=None 기본) — **영향 없음**.

Run: `cd backend && uv run pytest ../test/backend/management -q`
Expected: 전부 PASS. 이 회귀가 스펙 §8-7(activate·pause·budget-commit 경로도 원장 게이트 통과)을 커버한다 — 3곳이 issue_approval로 교체됐으므로 기존 activate/pause/budget 테스트가 실패하면 교체 누락 신호.
Run: `cd frontend && pnpm lint`
Expected: 에러 0

- [ ] **Step 7: Ruff + 커밋 (Task 4 산출물 포함 단일 커밋)**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/execution/executor.py backend/scripts/management_demo.py backend/api/routers/management.py backend/domain/management/wiring.py frontend/src/lib/api.ts test/backend/management/helpers.py test/backend/management/test_history_recorder.py test/backend/management/test_approval_ledger_gate.py test/backend/management/test_approve_endpoint.py
git commit -m "fix: 승인 원장 게이트(#5) 배선 — /approve 인증·approver 서버 주입·발행 4곳 일원화·executor approvals 필수화"
```

---

### Task 6: 집행 권장 게이트 정본화 — settings + contracts.policy + /exec-gate

**Files:**
- Modify: `backend/core/config.py` (management 섹션, 112행 근처)
- Modify: `backend/domain/management/contracts/policy.py` (함수 2개 추가)
- Modify: `backend/api/routers/management.py` (2523~2530행 `_is_executable_verdict` 교체 + GET /exec-gate 추가)
- Test: `test/backend/management/test_exec_gate.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/management/test_exec_gate.py` 신규 생성:

```python
# 집행 권장 게이트 — 경계값(클릭≥1% 포함·거부<20% 미만)·settings 폴백
from domain.management.contracts.policy import exec_gate_thresholds, is_executable_verdict


def test_boundary_click_intent_inclusive():
    # 클릭 의향률 1% 정확히는 통과(>=)
    assert is_executable_verdict(0.01, 0.0, min_cir=0.01, max_rej=0.2)
    assert not is_executable_verdict(0.0099, 0.0, min_cir=0.01, max_rej=0.2)


def test_boundary_rejection_exclusive():
    # 거부율 20% 정확히는 실패(<)
    assert is_executable_verdict(0.05, 0.19, min_cir=0.01, max_rej=0.2)
    assert not is_executable_verdict(0.05, 0.2, min_cir=0.01, max_rej=0.2)
    assert not is_executable_verdict(0.01, 0.2, min_cir=0.01, max_rej=0.2)


def test_thresholds_default_fallback():
    class _Empty:
        pass

    assert exec_gate_thresholds(_Empty()) == (0.01, 0.2)


def test_thresholds_read_settings():
    class _S:
        management_exec_gate_min_cir = 0.03
        management_exec_gate_max_rej = 0.15

    assert exec_gate_thresholds(_S()) == (0.03, 0.15)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_exec_gate.py -v`
Expected: FAIL — `ImportError: cannot import name 'exec_gate_thresholds'`

- [ ] **Step 3: contracts/policy.py에 정본 함수 추가** (파일 끝)

```python
# ── 집행 권장 게이트 (스펙 2026-07-07 §4) — 시뮬 결과의 집행 가능 판정 단일 정본 ──
# 잠정 기본값(시뮬팀 확인 대상): 클릭 의향률 ≥1%(포함) · 거부율 <20%(미만).
# 실측 calibration 해금 전까지 settings(management_exec_gate_*)로만 조정한다.

EXEC_GATE_DEFAULT_MIN_CIR: Final[float] = 0.01
EXEC_GATE_DEFAULT_MAX_REJ: Final[float] = 0.2


def exec_gate_thresholds(settings) -> tuple[float, float]:
    """settings에서 임계값을 읽는다(덕타이핑 — contracts는 core 미의존)."""
    return (
        float(getattr(settings, "management_exec_gate_min_cir", EXEC_GATE_DEFAULT_MIN_CIR)),
        float(getattr(settings, "management_exec_gate_max_rej", EXEC_GATE_DEFAULT_MAX_REJ)),
    )


def is_executable_verdict(
    click_intent_rate: float, rejection_rate: float, *, min_cir: float, max_rej: float
) -> bool:
    """집행 권장 판정 — 클릭 의향률은 하한 포함(>=), 거부율은 상한 미만(<)."""
    return click_intent_rate >= min_cir and rejection_rate < max_rej
```

(`Final`이 policy.py에 미임포트면 `from typing import Final` 추가.)

- [ ] **Step 4: config.py에 settings 추가**

`backend/core/config.py`의 `management_execution_mode` 선언(112행) 아래에 추가:

```python
    # 집행 권장 게이트 잠정값(시뮬팀 확인 대상) — 클릭 의향률 하한(포함)·거부율 상한(미만).
    # 판정 정본은 domain/management/contracts/policy.py — 여기 값은 코드 수정 없는 조정 채널.
    management_exec_gate_min_cir: float = 0.01
    management_exec_gate_max_rej: float = 0.2
```

- [ ] **Step 5: 라우터 정리 — `_is_executable_verdict` 위임 + GET /exec-gate**

(a) 임포트: `from domain.management.contracts.policy import ...` 라인에 `exec_gate_thresholds, is_executable_verdict` 추가.

(b) 2523~2530행의 `_is_executable_verdict` 전체("임시 TEST 해제" 주석 포함)를 교체:

```python
def _is_executable_verdict(click_intent_rate: float, rejection_rate: float) -> bool:
    """'집행 권장' 게이트 — 판정 정본은 contracts.policy, 임계값은 settings(잠정)."""
    min_cir, max_rej = exec_gate_thresholds(settings)
    return is_executable_verdict(
        click_intent_rate, rejection_rate, min_cir=min_cir, max_rej=max_rej
    )
```

(c) 그 위(2520행 근처, FromSimulationRequest 앞)에 임계값 조회 엔드포인트 추가:

```python
@router.get("/exec-gate")
async def exec_gate(user: User = Depends(get_current_user)):
    """집행 권장 게이트 임계값 — 프론트 판정 동기화용(판정 정본은 서버)."""
    min_cir, max_rej = exec_gate_thresholds(settings)
    return {"min_click_intent_rate": min_cir, "max_rejection_rate": max_rej}
```

- [ ] **Step 6: 통과 + 회귀 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_exec_gate.py -v`
Expected: 4 passed
Run: `cd backend && uv run pytest ../test/backend/management -q`
Expected: 전부 PASS (기존 from-simulation 테스트가 게이트 해제(0/1)를 전제했다면 임계값 통과 집계로 픽스처 수정)

- [ ] **Step 7: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/core/config.py backend/domain/management/contracts/policy.py backend/api/routers/management.py test/backend/management/test_exec_gate.py
git commit -m "edit: 집행 권장 게이트 settings 정본화(잠정 1%/20%) + GET /exec-gate — TEST 해제 복원"
```

---

### Task 7: 프론트 — 게이트 임계값 서버 동기화 (ExecuteFromSimulation)

**Files:**
- Modify: `frontend/src/lib/api.ts` (management 섹션, approve 근처)
- Modify: `frontend/src/components/manage/ExecuteFromSimulation.tsx`

- [ ] **Step 1: api.ts에 execGate 추가** — `approve:` 정의 바로 위에:

```typescript
    // 집행 권장 게이트 임계값 — 판정 정본은 서버, 프론트는 버튼 활성/안내 동기화용
    execGate: () =>
      request<{ min_click_intent_rate: number; max_rejection_rate: number }>(
        "/management/exec-gate",
      ),
```

- [ ] **Step 2: ExecuteFromSimulation.tsx 수정**

(a) 9~12행의 임시 상수 블록 삭제:

```typescript
// 집행 권장 게이트 — 백엔드 _is_executable_verdict와 동기화.
// ⚠️ 임시(TEST): 게이트 해제 — 모든 결과 통과. 운영 복원 시 0.2 / 0.2로 되돌릴 것.
const EXEC_CIR = 0.0; // 클릭 의향률 ≥ 0% (원래 0.2)
const EXEC_REJ = 1.0; // 거부율 ≤ 100% (원래 0.2)
```

을 다음으로 교체:

```typescript
// 집행 권장 게이트 — 정본은 백엔드(GET /management/exec-gate). 아래는 조회 실패 시 폴백.
const DEFAULT_GATE = { min_click_intent_rate: 0.01, max_rejection_rate: 0.2 };
```

(b) 컴포넌트 본문 — 25행 `const executable = ...`을 게이트 state 기반으로 교체하고 마운트 시 1회 조회:

```typescript
  const [gate, setGate] = useState(DEFAULT_GATE);
  useEffect(() => {
    let alive = true;
    api.management
      .execGate()
      .then((g) => {
        if (alive) setGate(g);
      })
      .catch(() => {}); // 실패 시 DEFAULT_GATE 폴백
    return () => {
      alive = false;
    };
  }, []);
  const executable =
    clickIntentRate >= gate.min_click_intent_rate && rejectionRate < gate.max_rejection_rate;
```

(c) 기준 미달 안내문(114~120행)의 하드코딩 `20%`를 동적 값으로 교체:

```tsx
            {!executable && (
              <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-[12px] text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                집행 권장 기준 미달 — 클릭 의향률 {(clickIntentRate * 100).toFixed(1)}%(≥
                {(gate.min_click_intent_rate * 100).toFixed(0)}% 필요)· 거부율{' '}
                {(rejectionRate * 100).toFixed(1)}%(&lt;
                {(gate.max_rejection_rate * 100).toFixed(0)}% 필요). 기준을 충족해야 집행할 수
                있어요.
              </div>
            )}
```

- [ ] **Step 3: 검증**

Run: `cd frontend && pnpm lint`
Expected: 에러 0
Run: `cd frontend && pnpm build`
Expected: 빌드 성공

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/lib/api.ts frontend/src/components/manage/ExecuteFromSimulation.tsx
git commit -m "edit: 프론트 집행 게이트 임계값 서버 동기화(/exec-gate) — 하드코딩 TEST 해제 제거"
```

---

### Task 8: 알림 센터 launch_suggest 카드에 [집행하기] 연결

**Files:**
- Modify: `frontend/src/components/center/AlarmCenter.tsx` (334~348행 launch_suggest 분기)

- [ ] **Step 1: 구현**

(a) 임포트 추가(10행 근처):

```typescript
import { ExecuteFromSimulation } from '../manage/ExecuteFromSimulation';
```

(b) launch_suggest 분기(334~348행)를 교체 — payload에 캐시된 지표로 집행 모달을 그 자리에서 재사용(백엔드 훅이 게이트 통과 건만 생성하므로 버튼은 항상 활성 조건):

```tsx
      // launch_suggest — 집행 권장 게이트 통과 시 백엔드 훅이 생성(판정 정본은 서버).
      // payload에 캐시된 지표로 ExecuteFromSimulation 모달을 카드에서 바로 연다.
      const cir = Number(n.payload?.click_intent_rate ?? 0);
      const rej = Number(n.payload?.rejection_rate ?? 0);
      return (
        <div>
          {meta}
          <p className="mb-2">
            {pstr(n.payload, 'message') || '결과가 좋아요. 집행을 검토해 보세요.'}
          </p>
          <div className="flex items-center gap-2">
            {n.source_sim_id && (
              <ExecuteFromSimulation
                simulationId={n.source_sim_id}
                defaultName={pstr(n.payload, 'ad_title')}
                clickIntentRate={cir}
                rejectionRate={rej}
              />
            )}
            <button
              type="button"
              onClick={() => onIgnore(n)}
              disabled={busyId === n.id}
              className="rounded-lg border border-[#E5E8EB] px-3 py-1.5 text-xs text-[#4E5968] disabled:opacity-50 dark:border-[#2D3748] dark:text-[#9CA3AF]"
            >
              확인
            </button>
          </div>
        </div>
      );
```

(`n.source_sim_id` 타입이 `string | undefined`가 아니라 nullable이면 `n.source_sim_id ?? ''` 대신 조건부 렌더 유지 — 위 코드가 이미 조건부.)

- [ ] **Step 2: 검증**

Run: `cd frontend && pnpm lint`
Expected: 에러 0

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/center/AlarmCenter.tsx
git commit -m "add: 집행 제안(launch_suggest) 카드에서 바로 집행 — ExecuteFromSimulation 재사용"
```

---

### Task 9: launch_suggest 생성 훅 (⚠️ 시뮬 도메인 — 시뮬팀 확인 후 머지)

**Files:**
- Modify: `backend/domain/simulation/service/simulation_service.py` (97~128행 `_record_gen_suggestion` 아래 + 204행 호출부)
- Test: `test/backend/simulation/test_launch_suggestion.py`

**경계 규칙:** 시뮬 → `domain.management.contracts.policy`(contracts)만 import — 내부 직접 import 아님. 이 커밋은 시뮬팀 확인 전 push/머지 보류.

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/simulation/test_launch_suggestion.py` 신규 생성:

```python
# 시뮬 완료 → 집행 제안(launch_suggest) 훅 — 게이트 통과 시 생성·미달 시 미생성
from types import SimpleNamespace

from domain.simulation.service import simulation_service


def _request():
    return SimpleNamespace(
        project_id="proj-1",
        organization_id="org-1",
        ad_title="테스트 광고",
        user_id="user-1",
    )


def _result(cir: float, rej: float):
    return {
        "simulation_id": "sim-1",
        "aggregate": {"click_intent_rate": cir, "rejection_rate": rej},
    }


async def test_launch_suggest_created_when_gate_passes(monkeypatch):
    calls = []

    async def fake_create(**kw):
        calls.append(kw)

    monkeypatch.setattr(simulation_service, "create_center_suggestion", fake_create)
    await simulation_service._record_launch_suggestion(_request(), _result(0.02, 0.1))
    assert len(calls) == 1
    kw = calls[0]
    assert kw["suggestion_type"] == "launch_suggest"
    assert kw["dedup_key"] == "launch_suggest:sim-1"
    assert kw["payload"]["click_intent_rate"] == 0.02
    assert kw["payload"]["rejection_rate"] == 0.1


async def test_launch_suggest_skipped_below_gate(monkeypatch):
    calls = []

    async def fake_create(**kw):
        calls.append(kw)

    monkeypatch.setattr(simulation_service, "create_center_suggestion", fake_create)
    # 거부율 20% 정확히 = 실패(<) — 경계 검증
    await simulation_service._record_launch_suggestion(_request(), _result(0.02, 0.2))
    # 클릭 1% 미만 = 실패
    await simulation_service._record_launch_suggestion(_request(), _result(0.009, 0.0))
    assert calls == []


async def test_launch_suggest_skipped_without_persisted_sim(monkeypatch):
    calls = []

    async def fake_create(**kw):
        calls.append(kw)

    monkeypatch.setattr(simulation_service, "create_center_suggestion", fake_create)
    await simulation_service._record_launch_suggestion(
        _request(), {"simulation_id": None, "aggregate": {"click_intent_rate": 1.0, "rejection_rate": 0.0}}
    )
    assert calls == []
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/simulation/test_launch_suggestion.py -v`
Expected: FAIL — `AttributeError: ... has no attribute '_record_launch_suggestion'`

- [ ] **Step 3: 훅 구현 — `simulation_service.py`**

(a) 임포트 추가(파일 상단, 기존 임포트와 함께 — `settings`가 이미 임포트돼 있으면 중복 생략):

```python
from core.config import settings
from domain.management.contracts.policy import exec_gate_thresholds, is_executable_verdict
```

(b) `_record_gen_suggestion` 함수 끝의 TODO 주석(127행)을 삭제하고, 그 함수 아래에 추가:

```python
async def _record_launch_suggestion(request: SimulationRunRequest, result: dict) -> None:
    """집행 권장 게이트 통과 시 "집행 제안"(launch_suggest) 센터 알림을 인라인 생성.

    판정 정본은 management 집행 게이트(contracts.policy 재사용, 스펙 2026-07-07 §5) —
    알림 받은 건은 from-simulation 집행 게이트를 반드시 통과한다(409 UX 파탄 방지).
    영속화된 런(simulation_id 존재)에서만. best-effort·비차단(gen_suggest와 동일).
    """
    sim_id = result.get("simulation_id")
    if not sim_id or not request.project_id:
        return
    agg = result.get("aggregate") or {}
    cir = float(agg.get("click_intent_rate") or 0.0)
    rej = float(agg.get("rejection_rate") or 0.0)
    min_cir, max_rej = exec_gate_thresholds(settings)
    if not is_executable_verdict(cir, rej, min_cir=min_cir, max_rej=max_rej):
        return
    await create_center_suggestion(
        suggestion_type="launch_suggest",
        organization_id=request.organization_id,
        project_id=request.project_id,
        reason="sim_result_good",
        source_sim_id=sim_id,
        payload={
            "title": "집행 제안",
            "message": "시뮬 결과가 집행 권장 기준을 충족했어요. 이 광고로 캠페인 집행을 검토해 보세요.",
            "ad_title": request.ad_title,
            "click_intent_rate": cir,
            "rejection_rate": rej,
        },
        dedup_key=f"launch_suggest:{sim_id}",
    )
```

(c) 호출부 — 204행 `await _record_gen_suggestion(request, result)` 바로 아래에 추가:

```python
            # 집행 제안 — 집행 권장 게이트 통과 시에만 생성(정본: management contracts.policy).
            await _record_launch_suggestion(request, result)
```

- [ ] **Step 4: 통과 + 시뮬 회귀 확인**

Run: `cd backend && uv run pytest ../test/backend/simulation/test_launch_suggestion.py -v`
Expected: 3 passed
Run: `cd backend && uv run pytest ../test/backend/simulation -q`
Expected: 전부 PASS

- [ ] **Step 5: Ruff + 커밋 (⚠️ push·머지는 시뮬팀 확인 후)**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/simulation/service/simulation_service.py test/backend/simulation/test_launch_suggestion.py
git commit -m "add: 시뮬 완료 시 집행 제안(launch_suggest) 훅 — 집행 게이트 재사용(시뮬팀 확인 대상)"
```

---

### Task 10: 최종 검증

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `cd backend && uv run pytest ../test/backend -q`
Expected: 전부 PASS

- [ ] **Step 2: 프론트 빌드**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: 성공

- [ ] **Step 3: 팀 조율 체크(스펙 §6)**

- `core/models.py` 변경(Task 1) 팀 공지 여부 확인.
- Task 9 커밋의 push/머지 보류 상태 확인 — 시뮬팀에 "simulation_service에 훅 1개 추가, 기준은 management 집행 게이트(잠정 1%/20%) 재사용" 승인 요청.
