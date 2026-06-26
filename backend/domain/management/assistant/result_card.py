# 집행 결과를 ActionResult + 영속 ActionProposal로 결정적 카드화(LLM 미경유, 스펙 §5.5).
from __future__ import annotations

from domain.management.assistant.chat_cards.models import (
    ChatCard,
    ExecutionResultSection,
    TraceInfo,
)
from domain.management.contracts.enums import FailureReason, ResultStatus
from domain.management.contracts.schemas import ActionProposal, ActionResult

_EXPIRED = {FailureReason.PROPOSAL_EXPIRED, FailureReason.APPROVAL_EXPIRED}

_CARD_STATUS = {
    "success": "ok",
    "submitted_pending_review": "warning",
    "failed": "critical",
    "rejected": "neutral",
    "expired": "neutral",
    "already_executed": "neutral",
}

_FAILURE_TEXT = {
    "failed": "집행 중 문제가 발생해 적용되지 않았어요.",
    "expired": "제안이 만료돼 집행하지 않았어요. 다시 진단해 주세요.",
    "rejected": "정책상 챗에서 바로 집행할 수 없어요. 정식 승인 화면에서 처리해 주세요.",
    "already_executed": "이미 처리된 제안이에요.",
}


def map_result_status(status: ResultStatus, failure_reason: FailureReason | None) -> str:
    if status == ResultStatus.SUCCESS:
        return "success"
    if status == ResultStatus.SUBMITTED_PENDING_REVIEW:
        return "submitted_pending_review"
    if status == ResultStatus.REJECTED:
        return "rejected"
    if failure_reason in _EXPIRED:
        return "expired"
    if failure_reason == FailureReason.STALE_PROPOSAL:
        return "already_executed"
    return "failed"


def _summary(result_status: str, p: ActionProposal) -> str:
    if result_status == "success":
        return (
            f"일예산을 {p.budget_before_krw:,}원에서 {p.budget_after_krw:,}원으로 조정했어요."
            if p.action_type in ("INCREASE_BUDGET", "DECREASE_BUDGET")
            else f"{p.action_type} 집행을 완료했어요."
        )
    if result_status == "submitted_pending_review":
        return "Meta에 제출했고 검토 중이에요."
    return _FAILURE_TEXT.get(result_status, "처리되지 않았어요.")


def build_execution_result_card(
    *,
    proposal: ActionProposal,
    result: ActionResult | None,
    run_id: str | None,
    turn_id: str,
    result_status: str | None = None,
) -> ChatCard:
    """result가 있으면 그 status로, 없으면(실행 전 terminal) result_status 인자로 카드를 만든다."""
    if result is not None:
        rs = map_result_status(result.status, result.failure_reason)
    else:
        rs = result_status
    assert rs is not None, "result 또는 result_status 중 하나는 필요"
    sec = ExecutionResultSection(
        title="집행 결과",
        action_type=proposal.action_type,
        result_status=rs,
        proposal_id=proposal.proposal_id,
        preview_id=proposal.evidence_metrics.get("preview_id"),
        budget_before_krw=proposal.budget_before_krw,
        budget_after_krw=proposal.budget_after_krw,
        run_id=run_id,
        summary=_summary(rs, proposal),
        failure_reason=(
            _FAILURE_TEXT.get(rs) if rs not in ("success", "submitted_pending_review") else None
        ),
    )
    return ChatCard(
        type="management", status=_CARD_STATUS[rs], sections=[sec], trace=TraceInfo(turn_id=turn_id)
    )
