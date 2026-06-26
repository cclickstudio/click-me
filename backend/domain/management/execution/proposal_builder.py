# DiagnosticResult(최신 진단)의 proposal_preview를 정본 ActionProposal로 승격한다.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from domain.management.approval import judge_tier
from domain.management.assistant.contracts import DiagnosticResult
from domain.management.contracts.enums import ActionTier, ProposalStatus
from domain.management.contracts.schemas import ActionProposal, finalize_proposal

#: 챗 버튼(단일 승인)으로 집행 가능한 최대 Tier. 초과(예: TIER_3)는 정식 승인 필요(§5.4).
#: 정책 권위는 approval.py — 이 컷오프는 FE 노출용 신호이며 approve()가 최종 강제한다.
CHAT_EXECUTABLE_MAX_TIER = ActionTier.TIER_2


def requires_external_approval(tier: ActionTier) -> bool:
    return tier > CHAT_EXECUTABLE_MAX_TIER


def build_action_proposal_from_diagnosis(
    dx: DiagnosticResult,
    *,
    tenant_id: str,
    ad_account_id: str,
    campaign_id: str,
    expected_state_version: str,
    approval_policy_version: str,
    preview_id: str | None = None,
    run_days: int = 7,
    ttl: timedelta = timedelta(minutes=10),
    now: datetime | None = None,
) -> ActionProposal:
    """ok+anomaly DiagnosticResult → finalize된 정본 ActionProposal. 호출 전 ok+anomaly 보장."""
    if dx.diagnostic_status != "ok" or not dx.anomaly or dx.proposal_preview is None:
        raise ValueError("build_action_proposal_from_diagnosis는 ok+anomaly에서만 호출")
    now = now or datetime.now(UTC)
    pv = dx.proposal_preview
    # 정본 tier는 프리뷰 라벨이 아니라 정책 권위(judge_tier=TIER_POLICY)에서 단일화한다.
    # finalize(requires_external_approval/표시 tier)와 decision(judge_tier)이 항상 일치한다.
    tier = judge_tier(pv.action_type)
    budget_after = pv.budget_after_krw or 0
    return finalize_proposal(
        ActionProposal(
            proposal_id=str(uuid4()),
            tenant_id=tenant_id,
            ad_account_id=ad_account_id,
            target_object_ids=(campaign_id,),
            action_type=pv.action_type,
            action_tier=tier,
            # preview_id는 trace용(ActionProposal 18필드 잠금 → evidence_metrics에 보관)
            evidence_metrics={
                "source": "chat_finalize",
                "confidence": dx.diagnosis.confidence if dx.diagnosis else 0.0,
                "preview_id": preview_id,
            },
            metrics_as_of=now,
            hypothesis=dx.diagnosis.hypothesis if dx.diagnosis else "",
            confidence=dx.diagnosis.confidence if dx.diagnosis else 0.0,
            expected_state_version=expected_state_version,
            budget_before_krw=pv.budget_before_krw or 0,
            budget_after_krw=budget_after,
            max_total_spend_krw=budget_after * run_days,
            expires_at=now + ttl,
            approval_policy_version=approval_policy_version,
            status=ProposalStatus.PENDING,
        )
    )
