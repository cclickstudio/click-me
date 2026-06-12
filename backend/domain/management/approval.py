"""★ 승인 플레인 — 승인의 '뇌' (🅰 소유, v2.0 핵심 결정 ①).

강제는 executor(🅱), 입은 오케스트레이터(별도 담당). 여기서는 판정만 한다.
정책 값은 contracts/policy.py 단일 소스에서 읽는다 — 하드코딩 금지 (R&R §8).
executor의 승인 후 4단계 검증과 의도적으로 중복된다 (defense in depth, 불변 규칙 #4).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from domain.management.contracts.enums import ActionTier, ExecutionMode
from domain.management.contracts.policy import (
    APPROVAL_POLICY_VERSION,
    APPROVAL_TTL_MINUTES,
    AUTO_APPROVE_MAX_TIER,
    TIER_POLICY,
)
from domain.management.contracts.schemas import (
    ActionProposal,
    ApprovedAction,
    compute_proposal_hash,
    proposal_hash_payload,
)


def judge_tier(action_type: str) -> ActionTier:
    """P1 정책표 판정 (정본). 미등록 action_type은 보수적으로 Tier 3."""
    return TIER_POLICY.get(action_type, ActionTier.TIER3)


def requires_human(tier: ActionTier) -> bool:
    return tier > AUTO_APPROVE_MAX_TIER


def relabel_if_mismatch(proposal: ActionProposal) -> tuple[ActionProposal, bool]:
    """라벨≠판정이면 판정 Tier로 재라벨 후 진행 (상향 재라벨은 감사 로그 대상)."""
    judged = judge_tier(proposal.action_type)
    if judged == proposal.action_tier:
        return proposal, False
    return proposal.model_copy(update={"action_tier": judged}), True


def validate_proposal(proposal: ActionProposal, now: datetime | None = None) -> list[str]:
    """승인 전 3단계 검증 — 만료 / 해시(변조) / 정책 버전."""
    now = now or datetime.now(UTC)
    issues: list[str] = []
    if proposal.expires_at <= now:
        issues.append(f"제안 만료됨 (expires_at={proposal.expires_at.isoformat()})")
    if compute_proposal_hash(proposal_hash_payload(proposal)) != proposal.proposal_hash:
        issues.append("proposal_hash 불일치 — 제안 변조 의심")
    if proposal.approval_policy_version != APPROVAL_POLICY_VERSION:
        issues.append(
            f"정책 버전 불일치 ({proposal.approval_policy_version} ≠ {APPROVAL_POLICY_VERSION})"
            " — STALE_PROPOSAL"
        )
    return issues


def approve(
    proposal: ActionProposal,
    approver_id: str,
    execution_mode: ExecutionMode = ExecutionMode.MOCK,
) -> ApprovedAction:
    """승인 발행. Tier 0~1 자율 통과는 approver_id='AUTO'로 호출한다."""
    now = datetime.now(UTC)
    return ApprovedAction(
        approved_action_id=f"appr_{uuid4().hex[:8]}",
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal.proposal_hash,
        tenant_id=proposal.tenant_id,
        approver_id=approver_id,
        action_tier=proposal.action_tier,
        approved_at=now,
        expires_at=now + timedelta(minutes=APPROVAL_TTL_MINUTES),
        approval_policy_version=APPROVAL_POLICY_VERSION,
        expected_state_version=proposal.expected_state_version,
        execution_mode=execution_mode,
    )
