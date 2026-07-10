# 리밸런스(REBALANCE_BUDGET) 원자 집행 — 전용 경로·보상·멱등·Tier2 게이트 검증
"""executor._call_rebalance의 감액→증액→보상 시퀀스와 실패 시맨틱을 검증한다."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from domain.management.approval import issue_approval
from domain.management.contracts.enums import (
    ActionTier,
    ExecutionMode,
    FailureReason,
    ResultStatus,
)
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION
from domain.management.contracts.schemas import (
    ActionProposal,
    ActionResult,
    finalize_proposal,
)
from domain.management.execution.approval_stores import InMemoryApprovalStore
from domain.management.execution.audit_log import InMemoryAuditLog
from domain.management.execution.executor import (
    AUTO_APPROVER,
    Executor,
    InMemoryIdempotencyStore,
)
from domain.management.execution.tier import BudgetAuthority


class FakeRebalanceWriter:
    """adjust_budget만 구현한 fake — 파생 멱등키 suffix(dec|inc|comp)로 실패·pending 주입."""

    def __init__(self, fail: set[str] | None = None, pending: set[str] | None = None):
        self.calls: list[tuple[str, int, str]] = []
        self.fail = fail or set()
        self.pending = pending or set()

    async def adjust_budget(self, campaign_id: str, amount_krw: int, idem_key: str) -> ActionResult:
        self.calls.append((campaign_id, amount_krw, idem_key))
        leg = idem_key.rsplit(":", 1)[-1]
        if leg in self.fail:
            status, reason = ResultStatus.FAILED, FailureReason.PLATFORM_ERROR
        elif leg in self.pending:
            status, reason = ResultStatus.SUBMITTED_PENDING_REVIEW, None
        else:
            status, reason = ResultStatus.SUCCESS, None
        return ActionResult(
            result_id=uuid4().hex,
            approval_id="",
            status=status,
            failure_reason=reason,
            executed_at=datetime.now(UTC),
            idempotency_key=idem_key,
        )


async def _state_v1(_ad_account_id: str) -> str:
    return "state_v1"


def make_rebalance_proposal(**overrides) -> ActionProposal:
    now = datetime.now(UTC)
    base = dict(
        proposal_id=f"prop_{uuid4().hex[:8]}",
        tenant_id="tenant-1",
        ad_account_id="act_1",
        target_object_ids=("camp_from", "camp_to"),
        action_type="REBALANCE_BUDGET",
        action_tier=ActionTier.TIER_2,
        evidence_metrics={
            "from_before_krw": 50_000,
            "from_after_krw": 40_000,
            "to_before_krw": 30_000,
            "to_after_krw": 40_000,
            "move_krw": 10_000,
        },
        metrics_as_of=now,
        hypothesis="테스트 리밸런스",
        confidence=1.0,
        expected_state_version="state_v1",
        budget_before_krw=80_000,
        budget_after_krw=80_000,
        max_total_spend_krw=0,
        expires_at=now + timedelta(minutes=10),
        approval_policy_version=APPROVAL_POLICY_VERSION,
    )
    base.update(overrides)
    return finalize_proposal(ActionProposal(**base))


def build_rebalance_executor(writer, approvals) -> Executor:
    return Executor(
        writer,
        idempotency=InMemoryIdempotencyStore(),
        audit=InMemoryAuditLog(),
        budget_for=lambda _tenant: BudgetAuthority(limit_krw=10_000_000),
        state_version_provider=_state_v1,
        current_policy_version=APPROVAL_POLICY_VERSION,
        approvals=approvals,
    )


async def _approved(proposal, approver="user-1", store=None):
    store = store or InMemoryApprovalStore()
    action = await issue_approval(
        proposal, approver, execution_mode=ExecutionMode.MOCK, store=store
    )
    return action, store


# ── Tier 2 게이트 ────────────────────────────────────────────────


async def test_tier2_auto_approver_blocked():
    """AUTO 승인 TIER_2는 INVALID_TIER로 거부(자율 실행 비활성 유지)."""
    writer = FakeRebalanceWriter()
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal, approver=AUTO_APPROVER)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.REJECTED
    assert result.failure_reason is FailureReason.INVALID_TIER
    assert writer.calls == []


# ── _call_rebalance 시퀀스 ────────────────────────────────────────


async def test_rebalance_success_two_legs_in_order():
    """사용자 승인 TIER_2 통과 + 감액(from)→증액(to) 순서·파생 멱등키(dec/inc)로 성공."""
    writer = FakeRebalanceWriter()
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.SUCCESS
    assert [(c[0], c[1]) for c in writer.calls] == [("camp_from", 40_000), ("camp_to", 40_000)]
    assert writer.calls[0][2].endswith(":camp_from:dec")
    assert writer.calls[1][2].endswith(":camp_to:inc")


async def test_rebalance_first_leg_failure_releases_idempotency():
    """감액 실패 = 아무것도 집행 안 됨 — 비-PARTIAL 실패, 멱등키 해제로 재시도 가능."""
    writer = FakeRebalanceWriter(fail={"dec"})
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)
    assert result.status is ResultStatus.FAILED
    assert result.failure_reason is FailureReason.PLATFORM_ERROR
    assert len(writer.calls) == 1  # 감액 1회만, 증액·보상 없음

    retry = await executor.execute(action, proposal)  # 멱등키 해제 → 재실행 가능
    assert len(writer.calls) == 2  # replay가 아니라 실제 재호출
    assert retry.status is ResultStatus.FAILED


async def test_rebalance_compensation_success_marks_and_restores():
    """증액 실패 + 보상 성공 = 원복 완료 — 비-PARTIAL 실패 + compensation=succeeded."""
    writer = FakeRebalanceWriter(fail={"inc"})
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.FAILED
    assert result.failure_reason is FailureReason.PLATFORM_ERROR  # PARTIAL 아님
    calls = [(c[0], c[1]) for c in writer.calls]
    assert calls == [("camp_from", 40_000), ("camp_to", 40_000), ("camp_from", 50_000)]
    assert writer.calls[2][2].endswith(":camp_from:comp")
    snaps = (result.platform_response_snapshot or {}).get("targets") or []
    assert any(s.get("compensation") == "succeeded" for s in snaps)


async def test_rebalance_compensation_success_allows_reexecution():
    """보상 성공 후 같은 승인(TTL 내) 재실행은 의도된 동작 — 멱등키 해제로 실제 재호출.

    승인 원장은 consumed로 거부하지 않고(재제출 차단은 멱등 게이트 담당 — executor 주석),
    사용자가 승인한 동일 transfer의 일시 실패는 새 카드 없이 재시도 가능해야 한다.
    """
    writer = FakeRebalanceWriter(fail={"inc"})
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    first = await executor.execute(action, proposal)
    assert first.failure_reason is FailureReason.PLATFORM_ERROR
    calls_after_first = len(writer.calls)  # dec, inc, comp = 3

    writer.fail = set()  # 이번엔 증액 성공
    second = await executor.execute(action, proposal)
    assert second.status is ResultStatus.SUCCESS
    assert len(writer.calls) == calls_after_first + 2  # dec, inc 실제 재호출


async def test_rebalance_compensation_failure_is_sealed():
    """증액·보상 모두 실패 = 부분 변경 방치 — PARTIAL_FAILURE 박제, 같은 승인 재집행 차단."""
    writer = FakeRebalanceWriter(fail={"inc", "comp"})
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)
    assert result.status is ResultStatus.FAILED
    assert result.failure_reason is FailureReason.PARTIAL_FAILURE
    snaps = (result.platform_response_snapshot or {}).get("targets") or []
    assert any(s.get("compensation") == "failed" for s in snaps)

    calls_before = len(writer.calls)
    replayed = await executor.execute(action, proposal)  # 박제 결과 재생, writer 미호출
    assert replayed.failure_reason is FailureReason.PARTIAL_FAILURE
    assert len(writer.calls) == calls_before


async def test_rebalance_pending_leg_is_sealed_without_compensation():
    """SUBMITTED_PENDING_REVIEW 등 불확정 다리는 보상 없이 박제 — SUCCESS만 성공으로 본다.

    불확정 다리는 나중에 적용될 수 있어 진행(성공 오판)도 보상(이중 변경)도 위험하다.
    """
    writer = FakeRebalanceWriter(pending={"inc"})
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.FAILED
    assert result.failure_reason is FailureReason.PARTIAL_FAILURE
    assert len(writer.calls) == 2  # dec, inc — 보상(comp) 호출 없음
    snaps = (result.platform_response_snapshot or {}).get("targets") or []
    assert not any(s.get("compensation") for s in snaps)
    assert any(s.get("indeterminate") for s in snaps)


# ── 계약 불변식 방어 (executor = 최종 지출 게이트) ─────────────────


async def test_rebalance_missing_evidence_fails_without_calls():
    """evidence_metrics 필드 누락은 writer 호출 전 실패."""
    writer = FakeRebalanceWriter()
    proposal = make_rebalance_proposal(evidence_metrics={"move_krw": 10_000})
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.FAILED
    assert writer.calls == []


async def test_rebalance_move_mismatch_fails_without_calls():
    """감액분≠move 등 불변식 위반은 writer 호출 전 실패 — 라우터를 신뢰하지 않는다."""
    writer = FakeRebalanceWriter()
    proposal = make_rebalance_proposal(
        evidence_metrics={
            "from_before_krw": 50_000,
            "from_after_krw": 40_000,
            "to_before_krw": 30_000,
            "to_after_krw": 45_000,  # 증액분 15,000 ≠ move 10,000
            "move_krw": 10_000,
        }
    )
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.FAILED
    assert writer.calls == []


async def test_rebalance_same_target_fails_without_calls():
    """동일 캠페인 from/to는 writer 호출 전 실패."""
    writer = FakeRebalanceWriter()
    proposal = make_rebalance_proposal(target_object_ids=("camp_from", "camp_from"))
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.FAILED
    assert writer.calls == []
