"""🅱 ExecutionService — ApprovedAction 소비 → executor 호출 (승인 로직 없음).

승인의 뇌 = approval.py(🅰) / 입 = 오케스트레이터(별도 담당) / 여기는 강제뿐.
stale 결과는 새 제안으로 이어진다 (P2: STALE_PROPOSAL → 새 제안, 자동 승계 금지)
— 재제안은 PENDING으로 저장만 하고, 재승인은 🅰 승인 플레인의 몫이다.
영속화(action_proposals 테이블, core.db get_db)는 공동 테이블 설계 후 Port 교체.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from domain.management.contracts.enums import FailureReason, ProposalStatus, ResultStatus
from domain.management.contracts.schemas import (
    ActionProposal,
    ActionResult,
    ApprovedAction,
    finalize_proposal,
)
from domain.management.execution.audit_log import AuditEvent, AuditSink
from domain.management.execution.executor import Executor

#: P3 TTL [안] — 재제안도 일반 24h (데모 모드는 주입으로 단축)
DEFAULT_REPROPOSAL_TTL = timedelta(hours=24)


def build_reproposal(
    proposal: ActionProposal,
    current_state_version: str,
    *,
    now: datetime | None = None,
    ttl: timedelta = DEFAULT_REPROPOSAL_TTL,
) -> ActionProposal:
    """stale 제안의 후속 제안 — 증거·가설은 승계하되 승인은 승계하지 않는다.

    새 proposal_id · 갱신된 expected_state_version · 리셋된 TTL · 재계산된 해시.
    """
    now = now or datetime.now(UTC)
    return finalize_proposal(
        proposal.model_copy(
            update={
                "proposal_id": str(uuid4()),
                "expected_state_version": current_state_version,
                "expires_at": now + ttl,
                "status": ProposalStatus.PENDING,
                "proposal_hash": "",
            }
        )
    )


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
    def __init__(
        self,
        executor: Executor,
        proposals: ProposalRepository,
        audit: AuditSink,
        *,
        state_version_provider=None,  # 재제안용 (ad_account_id → 현재 버전) — 미주입 시 재제안 생략
        reproposal_ttl: timedelta = DEFAULT_REPROPOSAL_TTL,
    ) -> None:
        self._executor = executor
        self._proposals = proposals
        self._audit = audit
        self._state_version_provider = state_version_provider
        self._reproposal_ttl = reproposal_ttl

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

    async def handle_with_recovery(
        self, action: ApprovedAction
    ) -> tuple[ActionResult, ActionProposal | None]:
        """실행 + stale 대응 — STALE_PROPOSAL이면 새 제안을 PENDING으로 저장해 함께 반환.

        재제안은 승인 없이 실행되지 않는다(자동 승계 금지) — 라우팅은 🅰 승인 플레인 몫.
        PARTIAL_FAILURE(halt)는 재제안하지 않는다 — P5의 "정지" 유지.
        """
        result = await self.handle(action)
        if (
            result.failure_reason is not FailureReason.STALE_PROPOSAL
            or self._state_version_provider is None
        ):
            return result, None
        stale = self._proposals.get(action.proposal_id)
        if stale is None:
            return result, None
        current_version = await self._state_version_provider(stale.ad_account_id)
        reproposal = build_reproposal(stale, current_version, ttl=self._reproposal_ttl)
        self._proposals.save(reproposal)
        self._audit.append(
            AuditEvent(
                category="execution_service.reproposed",
                tenant_id=action.tenant_id,
                proposal_id=reproposal.proposal_id,
                approval_id=action.approval_id,
                payload={"stale_proposal_id": stale.proposal_id},
            )
        )
        return result, reproposal

    @staticmethod
    def _next_status(result: ActionResult) -> ProposalStatus:
        if result.status in (ResultStatus.SUCCESS, ResultStatus.SUBMITTED_PENDING_REVIEW):
            return ProposalStatus.EXECUTED
        if result.failure_reason is None:
            return ProposalStatus.REJECTED
        return _STATUS_BY_FAILURE.get(result.failure_reason, ProposalStatus.REJECTED)
