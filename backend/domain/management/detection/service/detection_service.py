"""🅰 감지 파이프라인 — 관측 → 기대 비교 → 가드레일 → 결정론 진단 → (INCONCLUSIVE면) agent.

결정론으로 명확히 가려지면 agent를 부르지 않는다(비용·설명가능성). INCONCLUSIVE만 agent로
라우팅 → DiagnosisResult 단일 계약으로 🅱에 넘긴다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from domain.management.adapters.mock import MockAdPlatform
from domain.management.agents.diagnosis import run_diagnosis_agent
from domain.management.contracts.enums import DiagnosisStatus
from domain.management.contracts.fault_injection import FaultConfig
from domain.management.contracts.policy import DAILY_BUDGET_KRW
from domain.management.contracts.schemas import DiagnosisResult, MetricsSnapshot
from domain.management.detection.deterministic_dx import diagnose
from domain.management.detection.exposure_model import (
    expected_hourly_impressions,
    find_anomaly_window,
)
from domain.management.detection.guardrails import GuardResult, GuardVerdict, evaluate

_EVAL_TENANT = "org_eval"
_EVAL_CAMPAIGN = "camp_eval"


@dataclass(frozen=True)
class DetectionOutcome:
    guard: GuardResult
    diagnosis: DiagnosisResult | None  # NORMAL/INSUFFICIENT_DATA면 None
    expected: list[float]


def run_detection(
    tenant_id: str,
    campaign_id: str,
    snapshots: list[MetricsSnapshot],
    *,
    daily_budget_krw: int = DAILY_BUDGET_KRW,
    baseline_available: bool = True,
    use_agent: bool = True,
) -> DetectionOutcome:
    expected = expected_hourly_impressions(daily_budget_krw)
    observed = [s.impressions for s in snapshots]
    window = find_anomaly_window(expected, observed)
    guard = evaluate(
        expected, observed, anomaly_hours=window, baseline_available=baseline_available
    )

    if guard.verdict != GuardVerdict.DELIVERY_ANOMALY:
        return DetectionOutcome(guard, None, expected)

    dx = diagnose(tenant_id, campaign_id, snapshots, expected, window)
    if dx.status == DiagnosisStatus.INCONCLUSIVE and use_agent:
        dx = run_diagnosis_agent(dx, snapshots, expected, window)

    return DetectionOutcome(guard, dx, expected)


def run_detection_for_fault(
    fault: FaultConfig | None, *, seed: int = 42
) -> tuple[DiagnosisResult | None, GuardVerdict]:
    """eval/게이트 헬퍼 — Mock 게재 1일치 생성 후 감지 파이프라인을 돌린다."""
    day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    snapshots = asyncio.run(
        MockAdPlatform(seed=seed).fetch_hourly_metrics(_EVAL_CAMPAIGN, day, fault)
    )
    outcome = run_detection(
        _EVAL_TENANT, _EVAL_CAMPAIGN, snapshots, daily_budget_krw=DAILY_BUDGET_KRW
    )
    return outcome.diagnosis, outcome.guard.verdict
