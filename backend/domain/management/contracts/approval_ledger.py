# 승인 원장 계약 — 서버 발행 승인의 진위 대조(집행 게이트 #5) 레코드·포트
"""발행부(approval.issue_approval)와 검증부(executor)가 이 계약만 공유한다.

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
