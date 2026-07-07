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
