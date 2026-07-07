# 승인 원장 — 레코드 생성/대조·인메모리 저장소·DB row 변환 (집행 게이트 #5 기반)
from datetime import UTC, datetime, timedelta

from management.helpers import NOW, make_action, make_proposal

from domain.management.contracts.approval_ledger import (
    record_from_action,
    record_mismatches,
)
from domain.management.contracts.enums import ExecutionMode
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION
from domain.management.execution.approval_stores import InMemoryApprovalStore


def _fresh_valid_proposal():
    """실시간 3단계 검증(만료·해시·정책버전)을 통과하는 제안."""
    now = datetime.now(UTC)
    return make_proposal(
        approval_policy_version=APPROVAL_POLICY_VERSION,
        metrics_as_of=now,
        expires_at=now + timedelta(hours=1),
    )


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


async def test_issue_approval_writes_ledger_record():
    from domain.management.approval import issue_approval

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
