"""🅱 ExecutionService — ApprovedAction 소비 → executor 호출 (승인 로직 없음).

승인의 뇌 = approval.py(🅰) / 입 = 오케스트레이터(별도 담당) / 여기는 강제뿐.
영속화(action_proposals 테이블, core.db get_db)는 공동 테이블 설계 후 Port 교체.
"""

from __future__ import annotations

from typing import Protocol

from domain.management.contracts.enums import FailureReason, ProposalStatus, ResultStatus
from domain.management.contracts.schemas import ActionProposal, ActionResult, ApprovedAction
from domain.management.execution.audit_log import AuditEvent, AuditSink
from domain.management.execution.executor import Executor

_STATUS_BY_FAILURE: dict[FailureReason, ProposalStatus] = {
    FailureReason.PROPOSAL_EXPIRED: ProposalStatus.EXPIRED,
    FailureReason.APPROVAL_EXPIRED: ProposalStatus.EXPIRED,
    FailureReason.STALE_PROPOSAL: ProposalStatus.STALE,
}


class ProposalRepository(Protocol):
    def get(self, proposal_id: str) -> ActionProposal | None: ...

    def save(self, proposal: ActionProposal) -> None: ...


class InMemoryProposalRepository:
    def __init__(self) -> None:
        self._proposals: dict[str, ActionProposal] = {}

    def get(self, proposal_id: str) -> ActionProposal | None:
        return self._proposals.get(proposal_id)

    def save(self, proposal: ActionProposal) -> None:
        self._proposals[proposal.proposal_id] = proposal


class ExecutionService:
    def __init__(self, executor: Executor, proposals: ProposalRepository, audit: AuditSink) -> None:
        self._executor = executor
        self._proposals = proposals
        self._audit = audit

    async def handle(self, action: ApprovedAction) -> ActionResult:
        proposal = self._proposals.get(action.proposal_id)
        if proposal is None:
            self._audit.append(
                AuditEvent(
                    category="execution_service.proposal_not_found",
                    tenant_id=action.tenant_id,
                    proposal_id=action.proposal_id,
                    approval_id=action.approval_id,
                )
            )
            return ActionResult(
                result_id=f"missing-{action.approval_id}",
                approval_id=action.approval_id,
                status=ResultStatus.REJECTED,
                failure_reason=FailureReason.STALE_PROPOSAL,
                idempotency_key="",
            )

        result = await self._executor.execute(action, proposal)
        self._proposals.save(proposal.model_copy(update={"status": self._next_status(result)}))
        return result

    @staticmethod
    def _next_status(result: ActionResult) -> ProposalStatus:
        if result.status in (ResultStatus.SUCCESS, ResultStatus.SUBMITTED_PENDING_REVIEW):
            return ProposalStatus.EXECUTED
        if result.failure_reason is None:
            return ProposalStatus.REJECTED
        return _STATUS_BY_FAILURE.get(result.failure_reason, ProposalStatus.REJECTED)
