"""골든 샘플 생성기 — 계약당 정상 1 + 경계 1 (§9.0 그라운드 룰).

contracts 변경(필드·해시 산식) 시 재실행해 픽스처를 갱신한다:
    cd backend && uv run python scripts/generate_golden_samples.py
"""
# ruff: noqa: E402 — sys.path 부트스트랩 후 import (스크립트 단독 실행 지원)

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.management.contracts.enums import (
    ActionTier,
    ExecutionMode,
    FailureReason,
    FaultMode,
    ProposalStatus,
    ResultStatus,
)
from domain.management.contracts.schemas import (
    AUTO_APPROVER,
    ActionProposal,
    ActionResult,
    ApprovedAction,
    FaultConfig,
    finalize_proposal,
)

OUT = Path(__file__).resolve().parents[1] / "domain/management/evals/fixtures/contracts"
NOW = datetime(2026, 6, 12, 9, 0, 0, tzinfo=UTC)  # 고정 — 픽스처 결정론 유지


def build_samples() -> dict[str, object]:
    proposal_normal = finalize_proposal(
        ActionProposal(
            proposal_id="prop-0001",
            tenant_id="org-1111",
            ad_account_id="act_001",
            target_object_ids=("camp-001",),
            action_type="PAUSE_CAMPAIGN",
            action_tier=ActionTier.TIER_1,
            evidence_metrics={
                "ctr": 0.001,
                "impressions_24h": 120,
                "expected_impressions_24h": 4800,
            },
            metrics_as_of=NOW,
            hypothesis="입찰 패배로 노출 급감 — 악화 광고 일시 중지",
            confidence=0.85,
            expected_state_version="sv-42",
            budget_before_krw=50_000,
            budget_after_krw=50_000,
            max_total_spend_krw=0,
            expires_at=NOW + timedelta(hours=24),
            approval_policy_version="approval-policy-v1",
            status=ProposalStatus.PENDING,
        )
    )
    proposal_edge = finalize_proposal(
        ActionProposal(
            proposal_id="prop-0002",
            tenant_id="org-1111",
            ad_account_id="act_001",
            target_object_ids=("camp-001", "camp-002"),
            action_type="REPLACE_CREATIVE",
            action_tier=ActionTier.TIER_3,
            evidence_metrics={
                "quality_ranking": "below_average_35",
                "candidates": [{"candidate_id": "cand-1", "sim_score": 0.72, "preview_url": None}],
            },
            metrics_as_of=NOW - timedelta(hours=25),
            hypothesis="품질 저하 — 시안 교체 제안",
            confidence=0.6,
            expected_state_version="sv-41",
            budget_before_krw=50_000,
            budget_after_krw=70_000,
            max_total_spend_krw=490_000,
            expires_at=NOW - timedelta(minutes=1),  # 경계: 이미 만료 (게이트 #2 픽스처)
            approval_policy_version="approval-policy-v1",
            status=ProposalStatus.PENDING,
        )
    )
    return {
        "action_proposal_normal.json": proposal_normal,
        "action_proposal_edge_expired.json": proposal_edge,
        "approved_action_normal.json": ApprovedAction(
            approval_id="appr-0001",
            proposal_id=proposal_normal.proposal_id,
            proposal_hash=proposal_normal.proposal_hash,
            tenant_id="org-1111",
            approver_id=AUTO_APPROVER,  # Tier 1 자율 통과
            action_tier=ActionTier.TIER_1,
            approved_at=NOW,
            expires_at=NOW + timedelta(minutes=15),  # P3: 제안 TTL보다 짧게
            approval_policy_version="approval-policy-v1",
            expected_state_version="sv-42",
            execution_mode=ExecutionMode.MOCK,
        ),
        "approved_action_edge_tier3.json": ApprovedAction(
            approval_id="appr-0002",
            proposal_id=proposal_edge.proposal_id,
            proposal_hash=proposal_edge.proposal_hash,
            tenant_id="org-1111",
            approver_id="user-77",  # Tier 3 건별 사용자 승인
            action_tier=ActionTier.TIER_3,
            approved_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
            approval_policy_version="approval-policy-v1",
            expected_state_version="sv-41",
            execution_mode=ExecutionMode.DRY_RUN,
        ),
        "action_result_normal.json": ActionResult(
            result_id="res-0001",
            approval_id="appr-0001",
            status=ResultStatus.SUCCESS,
            platform_response_snapshot={"targets": [{"target": "camp-001", "status": "success"}]},
            executed_at=NOW + timedelta(seconds=3),
            idempotency_key="3f1a" + "0" * 60,
        ),
        "action_result_edge_partial_failure.json": ActionResult(
            result_id="res-0002",
            approval_id="appr-0002",
            status=ResultStatus.FAILED,
            failure_reason=FailureReason.PARTIAL_FAILURE,  # 부분 실패 — 정지(P5)
            platform_response_snapshot={
                "targets": [
                    {"target": "camp-001", "status": "success"},
                    {"target": "camp-002", "status": "failed", "failure_reason": "timeout"},
                ]
            },
            executed_at=NOW + timedelta(seconds=7),
            idempotency_key="9b2c" + "0" * 60,
        ),
        "fault_config_normal.json": FaultConfig(mode=FaultMode.WRITE_TIMEOUT),
        "fault_config_edge_probabilistic.json": FaultConfig(
            mode=FaultMode.PARTIAL_FAILURE, probability=0.3
        ),
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, model in build_samples().items():
        (OUT / name).write_text(
            json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("wrote", name)
