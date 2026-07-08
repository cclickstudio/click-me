# executor 승인 원장 게이트(#5) — 위조 차단·필드 대조·소진 마킹·명시적 생략
from management.helpers import (
    NOW,
    POLICY_VERSION,
    STATE_VERSION,
    FakeWriter,
    build_executor,
    make_action,
    make_proposal,
)

from domain.management.contracts.approval_ledger import record_from_action
from domain.management.contracts.enums import ExecutionMode, FailureReason, ResultStatus
from domain.management.execution.approval_stores import InMemoryApprovalStore
from domain.management.execution.audit_log import InMemoryAuditLog
from domain.management.execution.executor import Executor, InMemoryIdempotencyStore
from domain.management.execution.tier import BudgetAuthority


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
