"""🅱 테스트 공용 헬퍼 — contracts만 import (🅰 내부 import 금지, 불변 규칙 §4-3)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from domain.management.contracts.enums import (
    ActionTier,
    ExecutionMode,
    FailureReason,
    FaultMode,
    ProposalStatus,
    ResultStatus,
)
from domain.management.contracts.schemas import (
    ActionProposal,
    ActionResult,
    ApprovedAction,
    FaultConfig,
    finalize_proposal,
)
from domain.management.execution.audit_log import InMemoryAuditLog
from domain.management.execution.executor import Executor, InMemoryIdempotencyStore
from domain.management.execution.tier import BudgetAuthority

NOW = datetime(2026, 6, 12, 9, 0, 0, tzinfo=UTC)
POLICY_VERSION = "approval-policy-v1"
STATE_VERSION = "sv-42"


def make_proposal(**overrides) -> ActionProposal:
    fields = {
        "proposal_id": str(uuid4()),
        "tenant_id": "org-1111",
        "ad_account_id": "act_001",
        "target_object_ids": ("camp-001",),
        "action_type": "pause",
        "action_tier": ActionTier.TIER_1,
        "evidence_metrics": {"ctr": 0.001},
        "metrics_as_of": NOW,
        "hypothesis": "입찰 패배로 노출 급감",
        "confidence": 0.8,
        "expected_state_version": STATE_VERSION,
        "budget_before_krw": 50_000,
        "budget_after_krw": 50_000,
        "max_total_spend_krw": 0,
        "expires_at": NOW + timedelta(hours=24),
        "approval_policy_version": POLICY_VERSION,
        "status": ProposalStatus.PENDING,
    }
    fields.update(overrides)
    return finalize_proposal(ActionProposal(**fields))


def make_action(proposal: ActionProposal, **overrides) -> ApprovedAction:
    fields = {
        "approval_id": str(uuid4()),
        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal.proposal_hash,
        "tenant_id": proposal.tenant_id,
        "approver_id": "user-77",
        "action_tier": proposal.action_tier,
        "approved_at": NOW,
        "expires_at": NOW + timedelta(minutes=15),
        "approval_policy_version": POLICY_VERSION,
        "expected_state_version": proposal.expected_state_version,
        "execution_mode": ExecutionMode.MOCK,
    }
    fields.update(overrides)
    return ApprovedAction(**fields)


class FakeWriter:
    """FaultConfig(contracts)로 고장을 켜는 가짜 Writer — Mock(🅰 소유)과 무관."""

    def __init__(
        self,
        fault: FaultConfig | None = None,
        fail_times: int = 0,
        fail_targets: set[str] | None = None,
    ):
        self.fault = fault
        self.fail_times = fail_times  # 처음 N회만 고장, 이후 성공
        self.fail_targets = fail_targets or set()
        self.calls: list[tuple[str, str, str]] = []  # (op, campaign_id, idem_key)

    async def pause(self, campaign_id: str, idem_key: str) -> ActionResult:
        return self._respond("pause", campaign_id, idem_key)

    async def adjust_budget(self, campaign_id: str, amount_krw: int, idem_key: str) -> ActionResult:
        return self._respond("adjust_budget", campaign_id, idem_key)

    def _respond(self, op: str, campaign_id: str, idem_key: str) -> ActionResult:
        self.calls.append((op, campaign_id, idem_key))
        if campaign_id in self.fail_targets:
            return self._failure(idem_key, FailureReason.PLATFORM_ERROR)
        if self.fault is not None and self.fail_times > 0:
            self.fail_times -= 1
            if self.fault.mode is FaultMode.WRITE_TIMEOUT:
                return self._failure(idem_key, FailureReason.TIMEOUT)
            if self.fault.mode is FaultMode.RATE_LIMITED:
                return self._failure(idem_key, FailureReason.RATE_LIMITED)
            if self.fault.mode is FaultMode.REVIEW_STUCK:
                return ActionResult(
                    result_id=str(uuid4()),
                    approval_id="",
                    idempotency_key=idem_key,
                    status=ResultStatus.SUBMITTED_PENDING_REVIEW,
                    executed_at=NOW,
                )
        return ActionResult(
            result_id=str(uuid4()),
            approval_id="",
            idempotency_key=idem_key,
            status=ResultStatus.SUCCESS,
            executed_at=NOW,
            platform_response_snapshot={"op": op, "campaign_id": campaign_id},
        )

    def _failure(self, idem_key: str, reason: FailureReason) -> ActionResult:
        return ActionResult(
            result_id=str(uuid4()),
            approval_id="",
            idempotency_key=idem_key,
            status=ResultStatus.FAILED,
            failure_reason=reason,
            executed_at=NOW,
        )


async def _no_sleep(_seconds: float) -> None:
    return None


def build_executor(
    writer: FakeWriter,
    *,
    limit_krw: int = 1_000_000,
    state_version: str = STATE_VERSION,
    policy: str = POLICY_VERSION,
    now: datetime = NOW,
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
        budget=budget,
        state_version_provider=state_provider,
        current_policy_version=policy,
        clock=lambda: now,
        sleep=_no_sleep,
    )
    return executor, audit, idem, budget
