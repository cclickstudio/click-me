"""🅰 MockAdPlatform — 일중 곡선 + 노이즈 + 고장모드 카탈로그 + 시계(데모 트리거).

원천 변수(cpm, base_ctr, 낙찰률, audience_size)만 직접 생성하고 나머지는 수식 파생
(meta-data-sources.md §4). 고장 주입은 원천 변수를 비트는 방식 → 주입한 FaultMode가
곧 eval 정답 라벨이 된다.
"""

import math
import random
from datetime import UTC, datetime

from domain.management.comparison.schemas import PostInsights, PostType
from domain.management.contracts.enums import CampaignState
from domain.management.contracts.fault_injection import FaultConfig, FaultMode
from domain.management.contracts.policy import (
    AUDIENCE_SIZE,
    BASE_CTR,
    CPM_ANCHOR_KRW,
    DAILY_BUDGET_KRW,
    HOURLY_PACING,
)
from domain.management.contracts.schemas import (
    AccountFunding,
    CampaignConfig,
    CampaignInfo,
    CreativePreview,
    DeliveryEstimate,
    DemographicMetrics,
    MetricsSnapshot,
    PlatformMetrics,
)

_FAULT_ONSET_HOUR = 14  # 고장 발현 시각 (일중 곡선상 오후 — 정상/이상 대비가 뚜렷)
_REVIEW_DELAY_UNTIL = 10  # 심사 지연: 이 시각 전까지 노출 0


class MockAdPlatform:
    """게재 시뮬레이터. 데모는 이 어댑터만으로 성립한다 (게이트 #9)."""

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)

    async def get_metrics(self, campaign_id: str, since: datetime) -> MetricsSnapshot:
        """단일 누적 스냅샷 — 하루 생성 후 마지막 시간행(누적 reach·impressions)을 반환.

        AdPlatformReader Port 충족(비교 서비스가 await로 호출). fault 없는 정상 게재 기준.
        """
        snapshots = await self.fetch_hourly_metrics(campaign_id, since)
        return snapshots[-1]

    async def get_state(self, campaign_id: str) -> CampaignState:
        """Port 충족 — mock은 항상 ACTIVE."""
        return CampaignState.ACTIVE

    async def list_campaigns(self) -> list[CampaignInfo]:
        """Port 충족 — 데모 캠페인 목록(고정). 라우터 데모 경로의 풍부한 고장 시나리오는
        _CAMPAIGNS_DEMO(라우터 소유)에 있고, 여기는 Port 일반 소비자용 최소 목록.
        """
        return [
            CampaignInfo(
                campaign_id="camp_1",
                name="여름 신상 원피스",
                state=CampaignState.ACTIVE,
                daily_budget_krw=200_000,
            ),
            CampaignInfo(
                campaign_id="camp_2",
                name="브랜드 데일리 룩",
                state=CampaignState.ACTIVE,
                daily_budget_krw=120_000,
            ),
        ]

    async def get_platform_breakdown(
        self, campaign_id: str, since: datetime
    ) -> list[PlatformMetrics]:
        """Port 충족 — 누적 지표를 IG/FB로 분해(데모 합성, 결정론 62/38)."""
        m = await self.get_metrics(campaign_id, since)
        split = (("instagram", 0.62), ("facebook", 0.38))
        return [
            PlatformMetrics(
                platform=p,
                impressions=int(m.impressions * f),
                clicks=int(m.clicks * f),
                spend_krw=int(m.spend_krw * f),
                reach=int(m.cum_reach * f),
            )
            for p, f in split
        ]

    async def get_demographic_breakdown(
        self, campaign_id: str, since: datetime
    ) -> list[DemographicMetrics]:
        """Port 충족 — 누적 지표를 연령×성별로 분해(데모 합성, 결정론 가중)."""
        m = await self.get_metrics(campaign_id, since)
        # 연령 버킷 가중 × 성별 분할(여 54 / 남 46) — 합 1.0
        age_w = (
            ("18-24", 0.22),
            ("25-34", 0.34),
            ("35-44", 0.24),
            ("45-54", 0.13),
            ("55-64", 0.07),
        )
        gender_w = (("female", 0.54), ("male", 0.46))
        return [
            DemographicMetrics(
                age=age,
                gender=gender,
                impressions=int(m.impressions * aw * gw),
                clicks=int(m.clicks * aw * gw),
                spend_krw=int(m.spend_krw * aw * gw),
                reach=int(m.cum_reach * aw * gw),
            )
            for age, aw in age_w
            for gender, gw in gender_w
        ]

    async def get_creatives(self, campaign_id: str) -> list[CreativePreview]:
        """Port 충족 — 데모 대표 시안 2개(이미지 없음 → 프론트 placeholder 카드)."""
        return [
            CreativePreview(
                ad_id=f"{campaign_id}_ad1",
                ad_name="메인 비주얼 A",
                headline="여름 신상 최대 50% 할인",
                primary_text="지금 만나보는 시즌 오프 특가, 놓치지 마세요.",
            ),
            CreativePreview(
                ad_id=f"{campaign_id}_ad2",
                ad_name="모델 컷 B",
                headline="데일리룩 완성",
                primary_text="가볍게 입기 좋은 데일리 아이템.",
            ),
        ]

    async def get_account_funding(self) -> AccountFunding:
        """Port 충족 — 데모는 잔액 충분(게재 차단 없음)."""
        return AccountFunding(
            account_status=1,
            available_balance_krw=1_000_000,
            spend_cap_krw=2_000_000,
            amount_spent_krw=1_000_000,
        )

    async def fetch_daily_metrics(self, campaign_id: str) -> list[dict]:
        """데모 일자별(3일) 합성(결정론) — 상세 차트·일자별 표용."""
        base = sum(ord(ch) for ch in campaign_id) % 2000
        out: list[dict] = []
        for i in range(3):
            impr = 900 + base + i * 120
            clicks = 30 + (base % 40) + i * 5
            spend = 4000 + base + i * 800
            out.append(
                {
                    "label": f"{i + 1}일차",
                    "impressions": impr,
                    "clicks": clicks,
                    "reach": int(impr * 0.95),
                    "spend_krw": spend,
                    "ctr": clicks / impr if impr else 0.0,
                    "cpc_krw": spend // clicks if clicks else 0,
                    "cpm_krw": int(spend / impr * 1000) if impr else 0,
                    "conversions": None,  # 데모는 전환 추적 미설정
                    "cvr": None,
                    "roas": None,
                }
            )
        return out

    async def get_estimate(self, config: CampaignConfig) -> DeliveryEstimate:
        """Port 충족 — audience 기반 간단 추정(결정론)."""
        return DeliveryEstimate(
            campaign_id=config.campaign_id,
            estimate_ready=True,
            estimate_mau_lower=AUDIENCE_SIZE // 2,
            estimate_mau_upper=AUDIENCE_SIZE,
            daily_outcomes_curve=(),
            as_of=datetime.now(UTC),
        )

    async def fetch_hourly_metrics(
        self,
        campaign_id: str,
        day: datetime,
        fault: FaultConfig | None = None,
        daily_budget_krw: int = DAILY_BUDGET_KRW,
    ) -> list[MetricsSnapshot]:
        """하루치 시간별 지표 생성. fault 주입 시 14시부터 해당 고장 증상 재현."""
        inject = fault is not None and self._rng.random() < fault.probability
        mode = fault.mode if (inject and fault is not None) else None

        # AUDIENCE_TOO_NARROW = 타겟 모수를 크게 줄여 reach 조기 포화 → frequency 폭등
        audience = AUDIENCE_SIZE
        if mode == FaultMode.AUDIENCE_TOO_NARROW:
            audience = 1_500  # 하루 누적 노출(~8천) 대비 작아 frequency가 5+로 치솟음

        snapshots: list[MetricsSnapshot] = []
        cum_impressions = 0.0
        prev_frequency = 1.0

        for hour in range(24):
            cpm = CPM_ANCHOR_KRW * self._rng.uniform(0.92, 1.08)
            win_rate = 1.0
            ctr_mult = 1.0

            if mode is not None and hour >= _FAULT_ONSET_HOUR:
                if mode == FaultMode.BID_LOSS:
                    # 경매가 급등 + 낙찰률 급감 → 예산 남는데 impressions 급감, cpm↑
                    cpm *= 1.5 + 0.05 * (hour - _FAULT_ONSET_HOUR)
                    win_rate = 0.25
                elif mode == FaultMode.REVIEW_REJECTED:
                    win_rate = 0.0  # DISAPPROVED — 노출 전면 중단
                elif mode == FaultMode.QUALITY_DEGRADED:
                    # 품질 저하 — ctr 빠른 감쇠 + 경매가 소폭(1.3배 미만) + 게재 경쟁력 하락
                    cpm *= 1.2
                    ctr_mult = max(0.3, 1.0 - 0.12 * (hour - _FAULT_ONSET_HOUR))
                    win_rate = 0.4
                elif mode == FaultMode.AUDIENCE_TOO_NARROW:
                    # 모수 소진 → 게재량 점감 (cum_reach는 작은 audience로 조기 포화)
                    win_rate = max(0.2, 0.6 - 0.05 * (hour - _FAULT_ONSET_HOUR))
            if mode == FaultMode.REVIEW_DELAY and hour < _REVIEW_DELAY_UNTIL:
                win_rate = 0.0  # 심사 지연 — 승인 전까지 노출 0

            spend = daily_budget_krw * HOURLY_PACING[hour] * win_rate
            impressions = spend / cpm * 1000

            # 빈도 피로: 누적 빈도가 오를수록 ctr 감쇠
            fatigue = max(0.55, 1.0 - 0.18 * max(0.0, prev_frequency - 1.0))
            ctr = BASE_CTR * self._rng.uniform(0.9, 1.1) * fatigue * ctr_mult
            clicks = impressions * ctr

            cum_impressions += impressions
            # 오디언스 포화 모델 — reach는 누적으로만 계산 (시간행 합산 금지)
            cum_reach = audience * (1 - math.exp(-cum_impressions / audience))
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


class MockOrganicReader:
    """OrganicInsightsReader 구현 — 오가닉 게시물 인사이트 mock (데모/eval 결정론)."""

    def __init__(self, seed: int = 7) -> None:
        self._rng = random.Random(seed)

    async def get_post_insights(self, post_id: str) -> PostInsights:
        reach = self._rng.randint(2000, 4000)
        impressions = int(reach * self._rng.uniform(1.3, 1.6))
        engagement = int(reach * self._rng.uniform(0.05, 0.08))
        return PostInsights(
            post_id=post_id,
            post_type=PostType.ORGANIC,
            as_of=datetime.now(UTC),
            reach=reach,
            impressions=impressions,
            engagement=engagement,
            clicks=0,
            spend_krw=0,
        )
