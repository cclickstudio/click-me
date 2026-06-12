"""🤝 매니지먼트 얇은 엔드포인트 — 감지·진단·승인(HITL) 플로우 노출.

오케스트레이터('입')의 소유는 미정(R&R §6) — 본 라우터는 데모용 최소 구현이며
판정 로직은 전부 domain.management(approval.py 등)에 위임한다.
무상태(stateless): 프론트가 받은 제안을 그대로 돌려보내고, proposal_hash 재검증으로
변조를 감지한다 (승인 전 3단계 검증 시연).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from domain.management.adapters.mock import MockAdPlatform
from domain.management.approval import (
    approve,
    relabel_if_mismatch,
    requires_human,
    validate_proposal,
)
from domain.management.contracts.fault_injection import FaultConfig, FaultMode
from domain.management.contracts.policy import DAILY_BUDGET_KRW
from domain.management.contracts.schemas import ActionProposal
from domain.management.demo import CAMPAIGN_ID, TENANT_ID, build_sample_proposal
from domain.management.detection.deterministic_dx import diagnose
from domain.management.detection.exposure_model import (
    expected_hourly_impressions,
    find_anomaly_window,
)

router = APIRouter()

_DEMO_FAULTS = {"bid_loss", "review_rejected", "none"}


@router.get("/run")
async def run_detection(fault: str = "bid_loss"):
    """감지 사이클 1회 실행: Mock 게재 → 기대 곡선 비교 → 결정론 진단 → 제안 검증."""
    if fault not in _DEMO_FAULTS:
        raise HTTPException(status_code=422, detail=f"fault는 {sorted(_DEMO_FAULTS)} 중 하나")

    fault_cfg = None if fault == "none" else FaultConfig(mode=FaultMode(fault))
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    snapshots = MockAdPlatform().fetch_hourly_metrics(CAMPAIGN_ID, today, fault_cfg)
    expected = expected_hourly_impressions(DAILY_BUDGET_KRW)
    window = find_anomaly_window(expected, [s.impressions for s in snapshots])

    payload: dict = {
        "fault": fault,
        "expected": [round(e, 1) for e in expected],
        "snapshots": [s.model_dump(mode="json") for s in snapshots],
        "anomaly_hours": window,
        "diagnosis": None,
        "proposal": None,
        "relabeled": False,
        "requires_human": False,
        "validation_issues": [],
    }
    if not window:
        return payload

    dx = diagnose(TENANT_ID, CAMPAIGN_ID, snapshots, expected, window)
    proposal = build_sample_proposal(dx)
    proposal, relabeled = relabel_if_mismatch(proposal)

    payload.update(
        diagnosis=dx.model_dump(mode="json"),
        proposal=proposal.model_dump(mode="json"),
        relabeled=relabeled,
        requires_human=requires_human(proposal.action_tier),
        validation_issues=validate_proposal(proposal),
    )
    return payload


class ApprovalRequest(BaseModel):
    proposal: ActionProposal
    approved: bool
    approver_id: str = "user_demo"


@router.post("/approve")
async def approve_proposal(body: ApprovalRequest):
    """승인 플레인 — 3단계 검증(만료/해시/정책 버전) 후 ApprovedAction 발행."""
    issues = validate_proposal(body.proposal)
    if issues:
        raise HTTPException(status_code=409, detail={"issues": issues})

    if not body.approved:
        return {
            "status": "rejected",
            "detail": "거절됨 — 무승인 액션은 어떤 경로로도 Writer에 도달 불가 (불변 규칙 #2)",
        }

    action = approve(body.proposal, body.approver_id)
    return {"status": "approved", "approved_action": action.model_dump(mode="json")}
