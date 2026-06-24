# 챗 집행 브릿지 — ProposedAction → ActionProposal 빌드 + 단일 지출경로(approve→executor) 실행.
"""단순 6액션만 mock/dry_run 집행.

창작/캠페인생성(REPLACE_CREATIVE·CREATE_CAMPAIGN)은 None(매니지먼트 UI 위임).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from domain.chat.contracts.agent_io import ProposedAction
    from domain.management.contracts.schemas import ActionProposal

# 데모 고정 배율 — policy 미제정, 추후 policy.py 상수화 예정.
_BUDGET_INCREASE_FACTOR = 1.5
_BUDGET_DECREASE_FACTOR = 0.7

_CHAT_EXECUTABLE = frozenset(
    {
        "PAUSE_CAMPAIGN",
        "DECREASE_BUDGET",
        "INCREASE_BUDGET",
        "ACTIVATE_CAMPAIGN",
        "EXPAND_AUDIENCE",
        "CHANGE_BID_STRATEGY",
    }
)


def _budget_after(action_type: str, before: int) -> int:
    if action_type == "INCREASE_BUDGET":
        return int(before * _BUDGET_INCREASE_FACTOR)
    if action_type == "DECREASE_BUDGET":
        return int(before * _BUDGET_DECREASE_FACTOR)
    return before


def build_chat_proposal(
    pa: ProposedAction, *, tenant_id: str, ad_account_id: str = "act_demo_001"
) -> ActionProposal | None:
    """ProposedAction → finalize된 ActionProposal. 비실행 액션이면 None."""
    if pa.action_type not in _CHAT_EXECUTABLE:
        return None
    from domain.management.approval import judge_tier  # noqa: PLC0415
    from domain.management.contracts.policy import (  # noqa: PLC0415
        APPROVAL_POLICY_VERSION,
        DAILY_BUDGET_KRW,
        PROPOSAL_TTL_MINUTES,
    )
    from domain.management.contracts.schemas import (  # noqa: PLC0415
        ActionProposal,
        ProposalStatus,
        finalize_proposal,
    )
    from domain.management.execution.tier import estimate_max_total_spend  # noqa: PLC0415

    before = pa.budget_after_krw or DAILY_BUDGET_KRW  # 데모 기준 예산
    after = _budget_after(pa.action_type, before)
    run_days = pa.run_days or 7
    p = ActionProposal(
        proposal_id=f"chat_{uuid4().hex[:8]}",
        tenant_id=tenant_id,
        ad_account_id=ad_account_id,
        target_object_ids=(pa.target_campaign_id or ad_account_id,),
        action_type=pa.action_type,
        action_tier=judge_tier(pa.action_type),
        evidence_metrics={"source": "chat_orchestrator"},
        metrics_as_of=datetime.now(UTC),
        hypothesis=pa.rationale,
        confidence=1.0,
        expected_state_version="state_v1",
        budget_before_krw=before,
        budget_after_krw=after,
        max_total_spend_krw=estimate_max_total_spend(after, run_days),
        expires_at=datetime.now(UTC) + timedelta(minutes=PROPOSAL_TTL_MINUTES),
        approval_policy_version=APPROVAL_POLICY_VERSION,
        status=ProposalStatus.PENDING,
    )
    return finalize_proposal(p)


async def execute_chat_action(
    pa: ProposedAction, *, tenant_id: str, approver_id: str, executor, execution_mode
):
    """ProposedAction을 단일 지출경로로 집행. 비실행 액션이면 None(위임).

    Raises:
        ValueError: validate_proposal 이슈 시 — 호출 노드(graph execute)가 try/except로 잡는다.
    """
    proposal = build_chat_proposal(pa, tenant_id=tenant_id)
    if proposal is None:
        return None
    from domain.management.approval import (  # noqa: PLC0415
        approve,
        relabel_if_mismatch,
        validate_proposal,
    )

    issues = validate_proposal(proposal)
    if issues:
        raise ValueError(f"proposal 검증 실패: {issues}")
    proposal, _ = relabel_if_mismatch(proposal)
    approved = approve(proposal, approver_id, execution_mode=execution_mode)
    return await executor.execute(approved, proposal)
