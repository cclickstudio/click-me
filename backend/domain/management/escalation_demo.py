"""🅱 에스컬레이션 데모 시나리오 detector — 단계가 쌓이면 회복하는 결정론 재탐지.

시나리오 노브는 🅱 detector에 둔다(🅰 MockAdPlatform은 무변경) — 도메인 경계 유지. 기존
fetch_hourly_metrics(fault) 그대로 호출하되, 집행된 단계 수에 따라 fault를 끄면 "회복"이 된다.
실연동 detector(실 지표·실 detection)로 교체해도 re_evaluate 로직은 그대로다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.management.adapters.mock import MockAdPlatform
from domain.management.contracts.enums import FaultMode
from domain.management.contracts.policy import DAILY_BUDGET_KRW
from domain.management.contracts.schemas import FaultConfig
from domain.management.detection.service.detection_service import (
    DetectionOutcome,
    run_detection,
)

if TYPE_CHECKING:
    from datetime import datetime


class DemoScenarioDetector:
    """executed_steps가 recover_after에 도달하면 fault를 끄고(=anomaly 소멸) 회복으로 본다."""

    def __init__(
        self,
        *,
        anomaly_fault: FaultMode = FaultMode.BID_LOSS,  # 데모 중심축 (CLAUDE.md)
        recover_after: int = 2,
        daily_budget_krw: int = DAILY_BUDGET_KRW,
        seed: int = 42,
    ) -> None:
        self._fault = anomaly_fault
        self._recover_after = recover_after
        self._daily_budget_krw = daily_budget_krw
        self._seed = seed

    async def detect(
        self, tenant_id: str, campaign_id: str, *, now: datetime, executed_steps: int
    ) -> DetectionOutcome:
        recovered = executed_steps >= self._recover_after
        fault = None if recovered else FaultConfig(mode=self._fault)
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        snapshots = await MockAdPlatform(seed=self._seed).fetch_hourly_metrics(
            campaign_id, day, fault, self._daily_budget_krw
        )
        return run_detection(
            tenant_id, campaign_id, snapshots, daily_budget_krw=self._daily_budget_krw
        )
