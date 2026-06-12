"""🅰 MockAdPlatform — 일중 곡선 + 노이즈 + 고장모드 카탈로그 + 시계(데모 트리거).

원천 변수(cpm, base_ctr, 낙찰률, audience_size)만 직접 생성하고 나머지는 수식 파생
(meta-data-sources.md §4). 고장 주입은 원천 변수를 비트는 방식 → 주입한 FaultMode가
곧 eval 정답 라벨이 된다.
"""

import math
import random
from datetime import datetime

from domain.management.contracts.fault_injection import FaultConfig, FaultMode
from domain.management.contracts.policy import (
    AUDIENCE_SIZE,
    BASE_CTR,
    CPM_ANCHOR_KRW,
    DAILY_BUDGET_KRW,
    HOURLY_PACING,
)
from domain.management.contracts.schemas import MetricsSnapshot


class MockAdPlatform:
    """게재 시뮬레이터. 데모는 이 어댑터만으로 성립한다 (게이트 #9)."""

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)

    def fetch_hourly_metrics(
        self,
        campaign_id: str,
        day: datetime,
        fault: FaultConfig | None = None,
        daily_budget_krw: int = DAILY_BUDGET_KRW,
    ) -> list[MetricsSnapshot]:
        """하루치 시간별 지표 생성. fault 주입 시 14시부터 해당 고장 증상 재현."""
        inject = fault is not None and self._rng.random() < fault.probability
        snapshots: list[MetricsSnapshot] = []
        cum_impressions = 0.0
        prev_frequency = 1.0

        for hour in range(24):
            cpm = CPM_ANCHOR_KRW * self._rng.uniform(0.92, 1.08)
            win_rate = 1.0

            if inject and fault is not None and hour >= 14:
                if fault.mode == FaultMode.BID_LOSS:
                    # 경매가 급등 + 낙찰률 급감 → 예산 남는데 impressions 급감, cpm↑
                    cpm *= 1.5 + 0.05 * (hour - 14)
                    win_rate = 0.25
                elif fault.mode == FaultMode.REVIEW_REJECTED:
                    win_rate = 0.0  # DISAPPROVED — 노출 전면 중단

            spend = daily_budget_krw * HOURLY_PACING[hour] * win_rate
            impressions = spend / cpm * 1000

            # 빈도 피로: 누적 빈도가 오를수록 ctr 감쇠
            fatigue = max(0.55, 1.0 - 0.18 * max(0.0, prev_frequency - 1.0))
            ctr = BASE_CTR * self._rng.uniform(0.9, 1.1) * fatigue
            clicks = impressions * ctr

            cum_impressions += impressions
            # 오디언스 포화 모델 — reach는 누적으로만 계산 (시간행 합산 금지)
            cum_reach = AUDIENCE_SIZE * (1 - math.exp(-cum_impressions / AUDIENCE_SIZE))
            frequency = cum_impressions / cum_reach if cum_reach > 0 else 1.0
            prev_frequency = frequency

            snapshots.append(
                MetricsSnapshot(
                    campaign_id=campaign_id,
                    as_of=day.replace(hour=hour, minute=0, second=0, microsecond=0),
                    impressions=int(impressions),
                    clicks=int(clicks),
                    inline_link_clicks=int(clicks * 0.9),
                    spend_krw=int(spend),
                    cum_impressions=int(cum_impressions),
                    cum_reach=int(cum_reach),
                    frequency=round(frequency, 3),
                    ctr=round(ctr, 5),
                    cpm_krw=int(cpm),
                    cpc_krw=int(spend / clicks) if clicks >= 1 else 0,
                )
            )
        return snapshots
