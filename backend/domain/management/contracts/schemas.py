"""contracts — Pydantic DTO.

CampaignConfig, MetricsSnapshot, DeliveryEstimate,
AnomalyEvent, DeliveryDiagnostics, ActionProposal, ActionResult.

공통 규칙 (R&R §2): UTC aware datetime(naive 금지) · 통화 KRW 정수(float 금지) ·
모든 계약에 schema_version 포함 · frozen=True.
"""

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from domain.management.contracts.enums import (
    ActionTier,
    AnomalyType,
    DiagnosisSource,
    DiagnosisStatus,
    ExecutionMode,
    ProposalStatus,
)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class MetricsSnapshot(_Frozen):
    """시간별(hourly) 지표 — reach/frequency는 누적값 (시간행 단순 합산 금지)."""

    campaign_id: str
    as_of: datetime
    impressions: int
    clicks: int
    inline_link_clicks: int
    spend_krw: int
    cum_impressions: int
    cum_reach: int
    frequency: float
    ctr: float
    cpm_krw: int
    cpc_krw: int
    schema_version: str = "1.0"


class DiagnosisResult(_Frozen):
    """🅰 → 🅱 (R&R §2.1). evidence_metrics 밖의 정보로 추론 금지(정보 방화벽)."""

    diagnosis_id: str
    tenant_id: str
    campaign_id: str
    anomaly_type: AnomalyType
    source: DiagnosisSource
    hypothesis: str
    confidence: float  # 결정론 경로는 1.0
    evidence_metrics: dict[str, Any]
    metrics_as_of: datetime
    status: DiagnosisStatus
    schema_version: str = "1.0"


class ActionProposal(_Frozen):
    """🅱 단독 생산 → 승인 플레인 (R&R §2.2 — 필드 18종 확정)."""

    proposal_id: str
    tenant_id: str
    ad_account_id: str
    target_object_ids: list[str]
    action_type: str
    action_tier: ActionTier  # 제안 라벨 — 판정 정본은 approval.py
    evidence_metrics: dict[str, Any]
    metrics_as_of: datetime
    hypothesis: str
    confidence: float
    expected_state_version: str
    budget_before: int  # KRW
    budget_after: int  # KRW
    max_total_spend: int  # KRW
    expires_at: datetime
    proposal_hash: str
    approval_policy_version: str
    status: ProposalStatus
    schema_version: str = "1.0"


class ApprovedAction(_Frozen):
    """승인 플레인(🅰) → executor(🅱) (R&R §2.3 — 확정 후 개정 불가)."""

    approved_action_id: str
    proposal_id: str
    proposal_hash: str  # executor 재검증용 (제안 변조 감지)
    tenant_id: str
    approver_id: str  # 사용자 ID 또는 "AUTO" (Tier 0~1 자율 통과)
    action_tier: ActionTier
    approved_at: datetime
    expires_at: datetime  # 승인 자체의 만료 (제안 만료와 별개, 더 짧다)
    approval_policy_version: str
    expected_state_version: str
    execution_mode: ExecutionMode
    schema_version: str = "1.0"


def proposal_hash_payload(proposal: ActionProposal) -> dict[str, Any]:
    """proposal_hash 산출 대상 필드 — 변조 감지의 범위 정의."""
    return {
        "proposal_id": proposal.proposal_id,
        "action_type": proposal.action_type,
        "target_object_ids": proposal.target_object_ids,
        "budget_after": proposal.budget_after,
        "max_total_spend": proposal.max_total_spend,
    }


def compute_proposal_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
