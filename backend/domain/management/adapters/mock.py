"""🅰 MockAdPlatform — 일중 곡선 + 노이즈 + 고장모드 카탈로그 + 시계(데모 트리거).

원천 변수(cpm, base_ctr, 낙찰률, audience_size)만 직접 생성하고 나머지는 수식 파생
(meta-data-sources.md §4). 고장 주입은 원천 변수를 비트는 방식 → 주입한 FaultMode가
곧 eval 정답 라벨이 된다.
"""

import math
import random
from datetime import UTC, datetime
from uuid import uuid4

from domain.management.comparison.schemas import PostInsights, PostType
from domain.management.contracts.enums import CampaignState, RelevanceRank, ResultStatus
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
    ActionResult,
    CampaignConfig,
    CampaignInfo,
    CreativePreview,
    DeliveryEstimate,
    DeliveryStatusDetail,
    DemographicMetrics,
    MetricsSnapshot,
    PlatformMetrics,
    RelevanceDiagnostics,
)

_FAULT_ONSET_HOUR = 14  # 고장 발현 시각 (일중 곡선상 오후 — 정상/이상 대비가 뚜렷)
_REVIEW_DELAY_UNTIL = 10  # 심사 지연: 이 시각 전까지 노출 0

# 데모 캠페인 시나리오 — list_campaigns·get_metrics 공유 단일 소스. 지표는 하드코딩하지 않고
# 예산·고장에서 파생한다(fetch_hourly_metrics가 policy.py 앵커로 증상 생성). 예산 리밸런싱이
# 판단하는 CPC 격차는 근거 있는 고장에서 자연히 나온다: 정상=고효율(CPC↓), 입찰 패배=저효율
# (CPM↑→CPC↑). 출처: meta-data-sources.md §3.2(분위)·§4.5(고장 매핑).
# (name, daily_budget_krw, fault) — 예산은 일예산 앵커(₩100,000) 스케일.
_DEMO_SCENARIOS: dict[str, tuple[str, int, FaultMode | None]] = {
    "camp_1": ("여름 신상 원피스", 100_000, None),  # 정상·고효율 → 리밸런싱 수혜(to)
    "camp_2": (
        "브랜드 데일리 룩",
        80_000,
        FaultMode.BID_LOSS,
    ),  # 입찰 패배·저효율 → 리밸런싱 출연(from)
    "camp_3": (
        "신규 런칭 티저",
        60_000,
        FaultMode.REVIEW_REJECTED,
    ),  # 게재 중단(노출 0) → 제외·이상 신호
}


class MockAdPlatform:
    """게재 시뮬레이터. 데모는 이 어댑터만으로 성립한다 (게이트 #9)."""

    def __init__(self, seed: int = 42, daily_budget_krw: int = DAILY_BUDGET_KRW) -> None:
        self._rng = random.Random(seed)
        self._budget = daily_budget_krw  # get_metrics 단일 스냅샷의 일예산(비교 데모가 주입)

    async def get_metrics(
        self, campaign_id: str, since: datetime, date_preset: str = "maximum"
    ) -> MetricsSnapshot:
        """단일 누적 스냅샷 — 하루 생성 후 마지막 시간행(누적 reach·impressions)을 반환.

        AdPlatformReader Port 충족(비교 서비스가 await로 호출). 데모 캠페인은 자기 시나리오의
        고장·예산을 그대로 태워(_DEMO_SCENARIOS) 근거 있는 지표를 낸다 — 예산 리밸런싱이
        읽는 CPC 격차가 여기서 생긴다. 시나리오 밖 id(비교 데모 등)는 기존대로 정상·주입 예산.
        date_preset은 실 reader 시그니처 일치용(데모는 무시).
        """
        _name, budget, fault = _DEMO_SCENARIOS.get(campaign_id, (None, self._budget, None))
        if fault is FaultMode.REVIEW_REJECTED:
            # 심사 거절(DISAPPROVED) — 전 구간 노출 0(이상 감지 no_delivery 신호). 클릭 0이라
            # 리밸런싱 대상에서 자연 제외된다 (검증 가이드 §2 방법 B).
            return MetricsSnapshot(
                campaign_id=campaign_id,
                as_of=since,
                impressions=0,
                clicks=0,
                inline_link_clicks=0,
                spend_krw=0,
                cum_impressions=0,
                cum_reach=0,
                frequency=0.0,
                ctr=0.0,
                cpm_krw=0,
                cpc_krw=0,
            )
        fault_cfg = FaultConfig(mode=fault) if fault is not None else None
        snapshots = await self.fetch_hourly_metrics(campaign_id, since, fault_cfg, budget)
        return snapshots[-1]

    async def get_account_spend(self, date_preset: str = "this_month") -> int:
        """Port 충족 — 데모는 0(예산 페이싱은 live에서만 의미)."""
        return 0

    async def get_account_daily_spend(self, date_preset: str = "this_month") -> list[dict]:
        """Port 충족 — 데모는 빈 곡선."""
        return []

    async def get_state(self, campaign_id: str) -> CampaignState:
        """Port 충족 — mock은 항상 ACTIVE."""
        return CampaignState.ACTIVE

    async def list_campaigns(self, include_archived: bool = False) -> list[CampaignInfo]:  # noqa: ARG002
        """Port 충족 — 데모 캠페인 목록. 시나리오 단일 소스(_DEMO_SCENARIOS)에서 빌드해
        예산·이름·상태가 get_metrics의 고장 데이터와 정합한다. 라우터 데모 경로의 풍부한
        목록(_CAMPAIGNS_DEMO)과는 별개(Port 일반 소비자용). (mock은 보관 개념 없어 무시.)
        """
        return [
            CampaignInfo(
                campaign_id=cid,
                name=name,
                state=CampaignState.ACTIVE,
                daily_budget_krw=budget,
            )
            for cid, (name, budget, _fault) in _DEMO_SCENARIOS.items()
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

    async def get_campaign_targeting(self, campaign_id: str) -> dict:
        """Port 충족 — 데모 캠페인 타겟팅·크리에이티브(결정론 고정값)."""
        targeting_by_id = {
            "camp_1": {
                "objective": "OUTCOME_SALES",
                "age_min": 20,
                "age_max": 39,
                "gender": "F",
                "ad_headline": "여름 신상 최대 50% 할인",
                "ad_body": "지금 만나보는 시즌 오프 특가, 놓치지 마세요.",
                "ad_image_url": None,
                "category_id": 3,
                "service_class": 25,
                "suggested_persona_count": 50,
            },
            "camp_2": {
                "objective": "OUTCOME_TRAFFIC",
                "age_min": 20,
                "age_max": 49,
                "gender": "",
                "ad_headline": "데일리룩 완성",
                "ad_body": "가볍게 입기 좋은 데일리 아이템.",
                "ad_image_url": None,
                "category_id": 3,
                "service_class": 25,
                "suggested_persona_count": 30,
            },
        }
        t = targeting_by_id.get(
            campaign_id,
            {
                "objective": "OUTCOME_TRAFFIC",
                "age_min": 18,
                "age_max": 65,
                "gender": "",
                "ad_headline": None,
                "ad_body": None,
                "ad_image_url": None,
                "category_id": 8,
                "service_class": 45,
                "suggested_persona_count": 20,
            },
        )
        # reach(원 도달수)는 데모 결정론값 — 표본 상한과 별개로 화면 표시용(실 reader와 shape 일치).
        return {
            "campaign_id": campaign_id,
            "campaign_name": campaign_id,
            "reach": t.get("suggested_persona_count", 20),
            **t,
        }

    async def get_account_funding(self) -> AccountFunding:
        """Port 충족 — 데모는 잔액 충분(게재 차단 없음)."""
        return AccountFunding(
            account_status=1,
            available_balance_krw=1_000_000,
            spend_cap_krw=2_000_000,
            amount_spent_krw=1_000_000,
        )

    async def get_relevance_diagnostics(self, campaign_id: str) -> RelevanceDiagnostics:
        """Port 충족 — 데모 정상 캠페인은 평균 등급(오탐 방지). 합성 금지 원칙상 단정 안 함."""
        return RelevanceDiagnostics(
            campaign_id=campaign_id,
            quality_ranking=RelevanceRank.AVERAGE,
            engagement_rate_ranking=RelevanceRank.AVERAGE,
            conversion_rate_ranking=RelevanceRank.AVERAGE,
            as_of=datetime.now(UTC),
        )

    async def get_spend_cap(self, campaign_id: str) -> int | None:
        """Port 충족 — 데모는 상한 미설정."""
        return None

    async def get_delivery_status_detail(self, campaign_id: str) -> DeliveryStatusDetail:
        """Port 충족 — 데모는 정상 게재(ACTIVE, 이슈 없음)."""
        return DeliveryStatusDetail(
            campaign_id=campaign_id,
            effective_status="ACTIVE",
            issues_info=(),
            learning_stage=None,
            as_of=datetime.now(UTC),
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
        cum_impressions = 0.0  # 다중일 누적 노출 베이스라인 (이전 날들의 reach 포화 반영)
        if mode == FaultMode.AUDIENCE_TOO_NARROW:
            # 빈도 피로는 단일일이 아니라 수일 누적으로 발생한다. 현실적으로 좁은 모수(3만)에
            # 이전 날들 누적 노출(모수×3 ≈ 9만)을 베이스라인으로 깔아, 관측일을 '모수를 이미 3회
            # 회전한 성숙 캠페인 일자'로 둔다 → 오늘 frequency 3+ 관측(다중일 포화 반영).
            audience = 30_000
            cum_impressions = audience * 3.0

        snapshots: list[MetricsSnapshot] = []
        prev_frequency = 1.0
        if cum_impressions > 0:  # 베이스라인 누적이 있으면 초기 빈도도 그에 맞춰 시작
            _reach0 = audience * (1 - math.exp(-cum_impressions / audience))
            prev_frequency = cum_impressions / _reach0 if _reach0 > 0 else 1.0

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

    def _ok(self, operation: str, idem_key: str) -> ActionResult:
        """성공 ActionResult 합성 — mock 쓰기 메서드 공통 반환값."""
        return ActionResult(
            result_id=str(uuid4()),
            approval_id="",
            status=ResultStatus.SUCCESS,
            platform_response_snapshot={"dry_run": True, "operation": operation},
            executed_at=datetime.now(UTC),
            idempotency_key=idem_key,
        )

    async def create_link_ad(
        self,
        config: CampaignConfig,
        adset_id: str,
        idem_key: str,
        *,
        page_id: str,
        image_hash: str | None = None,
    ) -> ActionResult:
        """mock — traffic 링크광고 생성(항상 성공)."""
        return self._ok("create_link_ad", idem_key)

    async def create_full_campaign(
        self, config: CampaignConfig, idem_key: str, *, page_id: str | None = None
    ) -> ActionResult:
        """mock 오케스트레이션 — 캠페인→광고세트→(traffic+link_url면 광고) 합성."""
        adset_result = self._ok("create_adset", f"{idem_key}-adset")
        if config.objective != "leads":
            if config.link_url:
                return self._ok("create_link_ad", f"{idem_key}-ad")
            return adset_result
        # leads: 폼→광고까지
        return self._ok("create_ad", f"{idem_key}-ad")


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
