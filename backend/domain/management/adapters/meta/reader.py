# 🤝 Meta 읽기 어댑터 — Insights / delivery_estimate / 상태 조회 (AdPlatformReader 구현)
"""AdPlatformReader 구현 — Graph API 실호출.

Graph API JSON → contracts Port 스키마 변환만 담당한다. 정책·진단 판단은 하지 않는다.
reader는 공동 소유(🅰 합의) — MetricsSnapshot 등 매핑 스키마의 스튜어드는 🅰이므로
필드 해석 변경 시 🅰 합의. import는 contracts·adapters.meta.client만 (경계 §5 유지).
spend/cpm/cpc 는 광고계정 통화가 KRW 라는 전제로 정수 KRW 로 매핑한다.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

from domain.management.adapters.meta.client import (
    MetaClient,
    build_meta_client,
    normalize_ad_account,
)
from domain.management.contracts.enums import CampaignState, RelevanceRank
from domain.management.contracts.schemas import (
    AccountFunding,
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

#: Meta effective_status → contracts CampaignState 매핑 (미등록 값은 DRAFT 보수 처리).
_STATE_MAP: dict[str, CampaignState] = {
    "ACTIVE": CampaignState.ACTIVE,
    "PAUSED": CampaignState.PAUSED,
    "CAMPAIGN_PAUSED": CampaignState.PAUSED,
    "ADSET_PAUSED": CampaignState.PAUSED,
    "IN_PROCESS": CampaignState.UNDER_REVIEW,
    "PENDING_REVIEW": CampaignState.UNDER_REVIEW,
    "PENDING_BILLING_INFO": CampaignState.UNDER_REVIEW,
    "PREAPPROVED": CampaignState.UNDER_REVIEW,
    "WITH_ISSUES": CampaignState.ACTIVE_PENDING_REVIEW,
    "DISAPPROVED": CampaignState.PAUSED,
    "DELETED": CampaignState.ENDED,
    "ARCHIVED": CampaignState.ARCHIVED,
    "COMPLETED": CampaignState.ENDED,
}

#: 트래픽 목표(클릭) — v1 스코프 (§7). delivery_estimate optimization_goal.
_TRAFFIC_OPTIMIZATION_GOAL = "LINK_CLICKS"

# Meta insights 조회 필드 (성과 읽기 핵심)
_INSIGHTS_FIELDS = (
    "impressions,clicks,inline_link_clicks,spend,reach,frequency,ctr,cpm,cpc,"
    "actions,action_values,purchase_roas,date_stop"
)

# 시간별(hourly breakdown) 조회 필드 — date_stop 불필요
_HOURLY_FIELDS = "impressions,clicks,inline_link_clicks,spend,reach,frequency,ctr,cpm,cpc"

# 캠페인 목록 조회 필드 — 대시보드 목록(이름·상태·예산·종료일). budget은 KRW(offset=1) 전제.
# lifetime_budget: 일예산 대신 총예산으로 설정된 캠페인(잠재고객/일정형) — 일예산 ₩0 오표기 방지.
# stop_time: Meta는 게재 기간이 끝나도 effective_status를 ACTIVE로 유지 → 종료 판별에 필요.
_CAMPAIGN_FIELDS = "id,name,effective_status,daily_budget,lifetime_budget,stop_time"

#: 보관 포함 조회용 effective_status — 기본 응답은 ACTIVE/PAUSED만이라 ARCHIVED를 명시 포함.
_ARCHIVED_STATUSES = '["ACTIVE","PAUSED","ARCHIVED","IN_PROCESS","WITH_ISSUES"]'

#: 데모 핀 — 삭제됐어도 전 페이지에 '종료됨'으로 고정 표시할 캠페인 id (발표용·운영 전 비우기).
#: 데이터(노출·리드·소재)는 insights로 그대로 조회되되 상태는 ENDED로 정직하게 표기한다
#: (실제 게재 중이 아니므로). 새로 추가되는 실 캠페인은 핀과 무관하게 실시간 상태로 유입된다.
_DEMO_PINNED_CAMPAIGN_IDS: frozenset[str] = frozenset({"120251028376650729"})

# 광고세트 예산·종료일 조회 필드 — 캠페인 노드에 예산/종료일이 없을 때(광고세트 일정) 보완.
_ADSET_FIELDS = "daily_budget,lifetime_budget,campaign_id,end_time"

# 플랫폼별 분해 조회 필드 — publisher_platform breakdown (FB/IG 등)
_PLATFORM_FIELDS = "impressions,clicks,spend,reach"

# 연령×성별 분해 조회 필드 — age,gender breakdown
_DEMOGRAPHIC_FIELDS = "impressions,clicks,spend,reach"

# Ad Relevance Diagnostics — 메타 본인 채점표 (광고 단위 백분위, meta-data-sources §2②)
_RELEVANCE_FIELDS = "quality_ranking,engagement_rate_ranking,conversion_rate_ranking"

# 상태·심사 상세 — 캠페인 노드 effective_status + 심사 이슈(meta-data-sources §3.1)
_STATUS_FIELDS = "effective_status,issues_info"

# 크리에이티브 조회 필드 — 이름 + creative(여러 이미지 소스·문구·썸네일).
# 동적/Advantage+ 광고는 image_url이 비고 asset_feed_spec.images 또는 object_story_spec에
# 원본이 있어, 고해상도 확보를 위해 가능한 소스를 모두 펼쳐 받는다.
_CREATIVE_FIELDS = (
    "name,creative{image_url,thumbnail_url,title,body,"
    "object_story_spec{link_data{picture},photo_data{url}},"
    "asset_feed_spec{images{url}}}"
)
_CREATIVE_LIMIT = 6  # 대표 시안만 — 너무 많으면 갤러리 과밀


def _pick_image(creative: dict[str, Any]) -> str | None:
    """가장 고해상도일 가능성이 높은 이미지 URL 선택 (동적 광고 우선)."""
    afs_images = (creative.get("asset_feed_spec") or {}).get("images") or []
    if afs_images and afs_images[0].get("url"):
        return afs_images[0]["url"]
    oss = creative.get("object_story_spec") or {}
    picture = (oss.get("link_data") or {}).get("picture")
    if picture:
        return picture
    photo = (oss.get("photo_data") or {}).get("url")
    if photo:
        return photo
    return creative.get("image_url")


# 계정 자금·게재 가능 조회 필드 — 선불 잔액 소진·계정 비활성 감지 + 지갑(한도·누적지출).
# KRW는 무소수 통화라 amount_spent·spend_cap이 그대로 원 단위 정수 문자열로 온다.
_FUNDING_FIELDS = "account_status,disable_reason,funding_source_details,amount_spent,spend_cap"

# 전환 이벤트별 Meta action_type — 같은 전환이 omni·pixel로 중복 집계될 수 있어
# 합산하지 않고 우선순위(앞이 우선)대로 첫 값만 쓴다. 캠페인이 구매를 안 팔아도
# 리드·가입·설치 중 실제 발생한 행동을 전환으로 센다(비이커머스 전환 의미화).
_CONVERSION_ACTION_TYPES: dict[str, tuple[str, ...]] = {
    "purchase": (
        "offsite_conversion.fb_pixel_purchase",
        "omni_purchase",
        "purchase",
    ),
    "lead": (
        "onsite_conversion.lead_grouped",  # Meta 즉석 양식(플랫폼 내부 리드)
        "offsite_conversion.fb_pixel_lead",  # 웹 픽셀 리드
        "lead",
    ),
    "signup": (
        "offsite_conversion.fb_pixel_complete_registration",
        "omni_complete_registration",
        "complete_registration",
    ),
    "install": (
        "mobile_app_install",
        "omni_app_install",
    ),
}

# 자동 감지 우선순위 — 실제 발생한 전환 중 구매에 가장 가까운 것부터 택1.
_CONVERSION_EVENT_PRIORITY: tuple[str, ...] = ("purchase", "lead", "signup", "install")


_RANK_VALUES: frozenset[str] = frozenset(r.value for r in RelevanceRank)


def _to_rank(value: Any) -> RelevanceRank:
    """Meta 랭킹 문자열 → RelevanceRank (미설정·저노출 'unknown' 포함, 미등록 값도 UNKNOWN)."""
    text = str(value or "").lower()
    return RelevanceRank(text) if text in _RANK_VALUES else RelevanceRank.UNKNOWN


def _to_int(value: Any) -> int:
    return int(round(float(value))) if value not in (None, "") else 0


def _to_float(value: Any) -> float:
    return float(value) if value not in (None, "") else 0.0


# (category_id, service_class) 키워드 매핑 — SIM_CATEGORIES 순서와 동기화.
# category_id는 프론트 simCategories.ts의 id(1-indexed), service_class는 NICE 류.
_CATEGORY_KEYWORDS: list[tuple[list[str], int, int]] = [
    (["댕댕", "강아지", "고양이", "반려", "애완", "펫", "pet"], 11, 45),
    (["피부", "미용", "화장품", "스킨케어", "뷰티", "헤어", "네일", "향수", "성형"], 4, 44),
    (["의류", "패션", "옷", "원피스", "티셔츠", "청바지", "신발", "가방", "쇼핑몰"], 3, 25),
    (["음식", "식당", "카페", "배달", "맛집", "커피", "음료", "빵", "디저트", "베이커리"], 2, 43),
    (
        ["앱", "app", "플랫폼", "소프트웨어", "ai", "인공지능", "saas", "it서비스", "서비스앱"],
        15,
        42,
    ),
    (["교육", "학원", "강의", "학습", "공부", "과외", "유튜브", "콘텐츠", "강좌"], 7, 41),
    (["여행", "관광", "호텔", "리조트", "운동", "스포츠", "피트니스", "헬스", "레저"], 6, 39),
    (["자동차", "차량", "렌트카", "카쉐어링", "오토바이", "자전거", "드라이브"], 12, 12),
    (["병원", "의원", "클리닉", "약국", "의료", "건강검진", "다이어트", "보험", "심리"], 5, 44),
    (["아기", "육아", "유아", "출산", "임신", "어린이", "키즈"], 10, 28),
    (["인테리어", "건축", "부동산", "가구", "이사", "리모델링", "청소"], 13, 36),
    (["서비스", "신청", "가입", "상담", "문의", "예약", "이용권"], 8, 45),
]


def _guess_category(text: str) -> tuple[int, int]:
    """광고 텍스트 → (category_id, service_class). 순서대로 첫 매칭."""
    t = text.lower()
    for keywords, cat_id, svc_cls in _CATEGORY_KEYWORDS:
        if any(k in t for k in keywords):
            return (cat_id, svc_cls)
    return (8, 45)  # 기본: 생활/편의서비스


def _extract_won(text: str) -> int | None:
    """'사용 가능한 잔액(₩5,000 KRW)' → 5000. 못 찾으면 None."""
    m = re.search(r"₩\s*([\d,]+)", text)
    return int(m.group(1).replace(",", "")) if m else None


def _values_by_action_type(items: Any) -> dict[str, float] | None:
    """Meta action 배열을 {action_type: value} 로 — 배열이 아니면(추적 데이터 없음) None."""
    if not isinstance(items, list):
        return None
    return {
        str(item.get("action_type")): _to_float(item.get("value"))
        for item in items
        if isinstance(item, dict)
    }


def _pick(values: dict[str, float], action_types: tuple[str, ...]) -> float | None:
    """우선순위대로 처음 일치하는 action_type 값 (없으면 None)."""
    for action_type in action_types:
        if action_type in values:
            return values[action_type]
    return None


def _count_conversions(actions: Any) -> tuple[float | None, str | None]:
    """실제 발생한 전환 건수와 그 이벤트명을 자동 감지로 돌려준다.

    actions가 배열이 아니면(전환 추적 미설정) (None, None) — 합성 금지·정직.
    배열이면 측정값이며, 우선순위로 데이터가 있는 첫 이벤트를 택1한다
    (구매를 안 파는 캠페인도 리드·가입·설치가 잡히면 그걸로 전환을 센다).
    어떤 전환도 없으면 (0.0, None) — 측정된 0.
    """
    values = _values_by_action_type(actions)
    if values is None:
        return None, None
    for event in _CONVERSION_EVENT_PRIORITY:
        hit = _pick(values, _CONVERSION_ACTION_TYPES[event])
        if hit is not None:
            return hit, event
    return 0.0, None


def _purchase_value(items: Any) -> float | None:
    """구매 매출·ROAS 배열에서 구매 값 하나만 고른다 (Meta 제공값, 구매 이벤트 한정)."""
    values = _values_by_action_type(items)
    return _pick(values, _CONVERSION_ACTION_TYPES["purchase"]) if values is not None else None


def _parse_date_utc(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    # Meta insights date_stop = 'YYYY-MM-DD' → 해당일 UTC 자정
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _is_past(value: str | None) -> bool:
    """Meta 일정 시각(예 '2026-06-19T15:34:00+0900')이 현재보다 과거면 True (게재 기간 종료)."""
    if not value:
        return False
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt < datetime.now(UTC)


def _parse_hour(label: str | None) -> int:
    """'14:00:00 - 14:59:59' → 14 (hourly breakdown 라벨 파싱)."""
    try:
        return int(str(label).split(":", 1)[0])
    except (TypeError, ValueError):
        return 0


class MetaAdsReader:
    """AdPlatformReader 구현 — wiring.py가 Port에 꽂는다."""

    def __init__(self, settings: object = None, *, client: MetaClient | None = None) -> None:
        self._client = client or build_meta_client(settings)

    async def get_metrics(
        self, campaign_id: str, since: datetime, date_preset: str = "maximum"
    ) -> MetricsSnapshot:
        # 기본 lifetime(maximum) 누적 1행. date_preset="this_month" 등 기간 한정 가능(예산 페이싱).
        # (since는 date_stop 없을 때 as_of 폴백으로만 사용)
        payload = await self._client.get(
            f"{campaign_id}/insights",
            {
                "fields": _INSIGHTS_FIELDS,
                "date_preset": date_preset,
            },
        )
        rows = payload.get("data", [])
        return self._row_to_metrics(rows[0] if rows else {}, campaign_id, since)

    async def get_metrics_by_campaign(
        self, campaign_ids: list[str], since: datetime, date_preset: str = "maximum"
    ) -> dict[str, MetricsSnapshot]:
        """계정 단위 캠페인별 지표 — level=campaign으로 한 응답에 모든 캠페인 행(N+1 제거).

        캠페인마다 /{id}/insights를 N번 부르던 걸 /act_{id}/insights 1콜(+페이징)로 대체한다.
        응답에 행이 없는(미게재) 캠페인은 campaign_ids 기준 0 스냅샷으로 채워, 호출자가
        누락 없이 캠페인별 룩업을 할 수 있게 한다(현 get_metrics 빈 데이터 동작과 동일).
        """
        account = normalize_ad_account(self._client.ad_account_id)
        params: dict[str, Any] = {
            "fields": f"{_INSIGHTS_FIELDS},campaign_id",
            "level": "campaign",
            "date_preset": date_preset,
            "limit": 500,
        }
        out: dict[str, MetricsSnapshot] = {}
        while True:
            payload = await self._client.get(f"{account}/insights", params)
            for row in payload.get("data", []):
                cid = str(row.get("campaign_id", ""))
                if not cid:
                    continue
                out[cid] = self._row_to_metrics(row, cid, since)
            paging = payload.get("paging", {})
            after = (paging.get("cursors") or {}).get("after")
            if not after or not paging.get("next"):
                break
            params = {**params, "after": after}
        # 미게재(행 없는) 캠페인 0 스냅샷 폴백 — 호출자 룩업 누락 방지.
        for cid in campaign_ids:
            out.setdefault(cid, self._row_to_metrics({}, cid, since))
        return out

    def _row_to_metrics(
        self, row: dict[str, Any], campaign_id: str, since: datetime
    ) -> MetricsSnapshot:
        """insights 행 1개 → MetricsSnapshot 변환. get_metrics·get_metrics_by_campaign 공용.

        빈 행({})이면 0 스냅샷 — 미게재 캠페인 폴백. since는 date_stop 없을 때 as_of 폴백.
        """
        impressions = _to_int(row.get("impressions"))
        clicks = _to_int(row.get("clicks"))
        reach = _to_int(row.get("reach"))
        inline_link_clicks = _to_int(row.get("inline_link_clicks"))
        spend_krw = _to_int(row.get("spend"))
        conv_count, conv_event = _count_conversions(row.get("actions"))
        conversions = int(round(conv_count)) if conv_count is not None else None
        # 매출·ROAS는 Meta가 구매 이벤트에만 값을 준다. 그 외 전환의 가치 환산은
        # 고객 통계(전환 가치) 기반 추정으로, service 레이어 책임(여기선 None 유지·정직).
        purchase_value_krw: int | None = None
        roas: float | None = None
        if conv_event == "purchase":
            purchase_value = _purchase_value(row.get("action_values"))
            purchase_value_krw = int(round(purchase_value)) if purchase_value is not None else None
            roas = _purchase_value(row.get("purchase_roas"))
            if roas is None and purchase_value_krw is not None:
                roas = purchase_value_krw / spend_krw if spend_krw else 0.0
        cvr = (
            conversions / inline_link_clicks
            if conversions is not None and inline_link_clicks
            else (0.0 if conversions == 0 else None)
        )
        return MetricsSnapshot(
            campaign_id=campaign_id,
            as_of=_parse_date_utc(row.get("date_stop"), since),
            impressions=impressions,
            clicks=clicks,
            inline_link_clicks=inline_link_clicks,
            spend_krw=spend_krw,  # 계정 통화 = KRW 전제 (정수)
            cum_impressions=impressions,  # 단일 스냅샷 — 누적은 호출자 책임
            cum_reach=reach,
            frequency=_to_float(row.get("frequency")),
            ctr=_to_float(row.get("ctr")) / 100.0,  # Meta ctr은 백분율 → 비율로 환산
            cpm_krw=_to_int(row.get("cpm")),
            cpc_krw=_to_int(row.get("cpc")),
            conversions=conversions,
            purchase_value_krw=purchase_value_krw,
            cvr=cvr,
            roas=roas,
        )

    async def get_estimate(self, config: CampaignConfig) -> DeliveryEstimate:
        account = normalize_ad_account(config.ad_account_id or self._client.ad_account_id)
        payload = await self._client.get(
            f"{account}/delivery_estimate",
            {"optimization_goal": _TRAFFIC_OPTIMIZATION_GOAL},
        )
        rows = payload.get("data", [])
        row: dict[str, Any] = rows[0] if rows else {}
        lower = _to_int(row.get("estimate_mau_lower_bound") or row.get("estimate_mau"))
        upper = _to_int(row.get("estimate_mau_upper_bound") or row.get("estimate_mau"))
        return DeliveryEstimate(
            campaign_id=config.campaign_id,
            estimate_ready=bool(row.get("estimate_ready", False)),
            estimate_mau_lower=lower,
            estimate_mau_upper=upper,
            daily_outcomes_curve=tuple(row.get("daily_outcomes_curve", [])),
            as_of=datetime.now(UTC),
        )

    async def get_state(self, campaign_id: str) -> CampaignState:
        payload = await self._client.get(campaign_id, {"fields": "effective_status,stop_time"})
        # 게재 기간이 끝났으면 effective_status가 ACTIVE라도 '종료'로 본다.
        if _is_past(payload.get("stop_time")):
            return CampaignState.ENDED
        status = str(payload.get("effective_status", "")).upper()
        return _STATE_MAP.get(status, CampaignState.DRAFT)

    async def get_spend_cap(self, campaign_id: str) -> int | None:
        """캠페인 평생 지출 상한(spend_cap, KRW). 안 걸려 있으면 None — 소진/상한 진행률 표시용."""
        payload = await self._client.get(campaign_id, {"fields": "spend_cap"})
        return _to_int(payload.get("spend_cap")) or None

    async def get_platform_breakdown(
        self, campaign_id: str, since: datetime
    ) -> list[PlatformMetrics]:
        """게재 플랫폼별(FB/IG 등) 지표 — insights breakdowns=publisher_platform (lifetime 누적)."""
        payload = await self._client.get(
            f"{campaign_id}/insights",
            {
                "fields": _PLATFORM_FIELDS,
                "breakdowns": "publisher_platform",
                "date_preset": "maximum",
            },
        )
        out: list[PlatformMetrics] = []
        for row in payload.get("data", []):
            out.append(
                PlatformMetrics(
                    platform=str(row.get("publisher_platform", "")),
                    impressions=_to_int(row.get("impressions")),
                    clicks=_to_int(row.get("clicks")),
                    spend_krw=_to_int(row.get("spend")),
                    reach=_to_int(row.get("reach")),
                )
            )
        return out

    async def get_demographic_breakdown(
        self, campaign_id: str, since: datetime
    ) -> list[DemographicMetrics]:
        """연령×성별(age,gender) 지표 — insights breakdowns=age,gender (lifetime 누적)."""
        payload = await self._client.get(
            f"{campaign_id}/insights",
            {
                "fields": _DEMOGRAPHIC_FIELDS,
                "breakdowns": "age,gender",
                "date_preset": "maximum",
            },
        )
        out: list[DemographicMetrics] = []
        for row in payload.get("data", []):
            out.append(
                DemographicMetrics(
                    age=str(row.get("age", "")),
                    gender=str(row.get("gender", "")),
                    impressions=_to_int(row.get("impressions")),
                    clicks=_to_int(row.get("clicks")),
                    spend_krw=_to_int(row.get("spend")),
                    reach=_to_int(row.get("reach")),
                )
            )
        return out

    async def get_creatives(self, campaign_id: str) -> list[CreativePreview]:
        """캠페인 대표 크리에이티브 — 산하 광고의 이름·썸네일(중첩 creative 필드).

        삭제·보관된 캠페인의 광고도 소재(이미지)는 Meta에 남아 있어, effective_status에
        ARCHIVED를 포함해 받아와 그전과 똑같이 대표 이미지를 보여준다.
        """
        payload = await self._client.get(
            f"{campaign_id}/ads",
            {
                "fields": _CREATIVE_FIELDS,
                "limit": _CREATIVE_LIMIT,
                "effective_status": _ARCHIVED_STATUSES,
            },
        )
        out: list[CreativePreview] = []
        for row in payload.get("data", []):
            creative = row.get("creative") or {}
            out.append(
                CreativePreview(
                    ad_id=str(row.get("id", "")),
                    ad_name=str(row.get("name", "")),
                    image_url=_pick_image(creative),
                    thumbnail_url=creative.get("thumbnail_url"),
                    headline=creative.get("title"),
                    primary_text=creative.get("body"),
                )
            )
        return out

    async def get_relevance_diagnostics(self, campaign_id: str) -> RelevanceDiagnostics:
        """Ad Relevance Diagnostics — 광고 단위 백분위(level=ad), 대표 1행 채택.

        메타는 광고(ad) 단위로만 랭킹을 준다. 캠페인 insights를 level=ad·lifetime으로 받아
        첫 행을 대표로 쓴다(없거나 저노출이면 전 필드 UNKNOWN — 합성 금지).
        """
        payload = await self._client.get(
            f"{campaign_id}/insights",
            {"fields": _RELEVANCE_FIELDS, "level": "ad", "date_preset": "maximum"},
        )
        rows = payload.get("data", [])
        row: dict[str, Any] = rows[0] if rows else {}
        return RelevanceDiagnostics(
            campaign_id=campaign_id,
            quality_ranking=_to_rank(row.get("quality_ranking")),
            engagement_rate_ranking=_to_rank(row.get("engagement_rate_ranking")),
            conversion_rate_ranking=_to_rank(row.get("conversion_rate_ranking")),
            as_of=datetime.now(UTC),
        )

    async def get_delivery_status_detail(self, campaign_id: str) -> DeliveryStatusDetail:
        """상태·심사·학습 상세 — 캠페인 effective_status·issues_info + 광고세트 learning_stage.

        get_state(CampaignState 요약)와 별개로 진단 신호 원본을 그대로 노출한다.
        """
        node, adsets = await asyncio.gather(
            self._client.get(campaign_id, {"fields": _STATUS_FIELDS}),
            self._client.get(f"{campaign_id}/adsets", {"fields": "learning_stage_info"}),
        )
        issues = tuple(
            str(it.get("error_message") or it.get("error_summary") or "").strip()
            for it in (node.get("issues_info") or [])
            if isinstance(it, dict)
        )
        # 광고세트 학습 단계 — 하나라도 LEARNING이면 학습 중으로 본다.
        learning: str | None = None
        for row in adsets.get("data", []):
            stage = (row.get("learning_stage_info") or {}).get("status")
            if stage:
                learning = str(stage)
                if str(stage).upper() == "LEARNING":
                    break
        return DeliveryStatusDetail(
            campaign_id=campaign_id,
            effective_status=str(node.get("effective_status", "")).upper(),
            issues_info=tuple(i for i in issues if i),
            learning_stage=learning,
            as_of=datetime.now(UTC),
        )

    async def get_min_daily_budget(self) -> int:
        """광고계정의 현재 최소 일예산(KRW)을 Meta에서 조회 — 정책 자동 최신화용.

        코드에 박지 않고 실시간 조회해, Meta가 통화 최소예산 정책을 바꾸면 자동으로 따라간다.
        """
        account = normalize_ad_account(self._client.ad_account_id)
        payload = await self._client.get(account, {"fields": "min_daily_budget"})
        return _to_int(payload.get("min_daily_budget"))

    async def get_account_funding(self) -> AccountFunding:
        """광고계정 게재 가능 여부 — 선불 잔액 0(소진)·계정 비활성 감지.

        잔액 소진 시 캠페인 effective_status는 ACTIVE로 남고 계정 status도 1이라,
        게재 중단을 알려면 funding_source_details(선불 가용 잔액)를 봐야 한다.
        """
        account = normalize_ad_account(self._client.ad_account_id)
        payload = await self._client.get(account, {"fields": _FUNDING_FIELDS})
        account_status = _to_int(payload.get("account_status"))
        fsd = payload.get("funding_source_details") or {}
        is_prepaid = _to_int(fsd.get("type")) == 20  # 20 = 선불(prepaid)
        available = _extract_won(str(fsd.get("display_string") or "")) if is_prepaid else None
        blocked, reason = False, None
        if account_status not in (1, 201):  # 1=active, 201=any_active
            blocked, reason = True, "계정 비활성"
        elif is_prepaid and available is not None and available <= 0:
            blocked, reason = True, "선불 잔액 부족"
        # 지출 한도·누적 지출 — 0이면 미설정(None)으로 둬서 프론트가 '한도 없음'을 구분.
        spend_cap = _to_int(payload.get("spend_cap")) or None
        amount_spent = _to_int(payload.get("amount_spent"))
        return AccountFunding(
            account_status=account_status,
            available_balance_krw=available,
            spend_cap_krw=spend_cap,
            amount_spent_krw=amount_spent,
            delivery_blocked=blocked,
            block_reason=reason,
        )

    async def _adset_info(self, account: str) -> dict[str, dict[str, Any]]:
        """캠페인별 광고세트 일예산 합 + 종료일 목록 — 캠페인 노드 정보 보완용.

        반환: ``{campaign_id: {"budget": int, "lifetime": int, "ends": [end_time | None, ...]}}``.
        budget/lifetime은 캠페인 노드에 예산이 없을 때(광고세트 예산), ends는 캠페인 stop_time이
        없을 때 게재 기간 종료 판별에 쓴다.
        """
        payload = await self._client.get(f"{account}/adsets", {"fields": _ADSET_FIELDS})
        info: dict[str, dict[str, Any]] = {}
        for row in payload.get("data", []):
            cid = str(row.get("campaign_id", ""))
            if not cid:
                continue
            entry = info.setdefault(cid, {"budget": 0, "lifetime": 0, "ends": []})
            entry["budget"] += _to_int(row.get("daily_budget"))  # KRW offset=1
            entry["lifetime"] += _to_int(row.get("lifetime_budget"))  # 총예산 광고세트
            entry["ends"].append(row.get("end_time"))
        return info

    @staticmethod
    def _schedule_ended(campaign_stop: str | None, adset_ends: list[str | None]) -> bool:
        """게재 기간 종료 여부 — 캠페인 stop_time 우선, 없으면 모든 광고세트 종료일이 과거일 때."""
        if campaign_stop:
            return _is_past(campaign_stop)
        # 캠페인 일정이 없으면 광고세트 기준 — 종료일이 다 있고 전부 과거여야 종료
        # (하나라도 무기한/미래면 진행 중)
        return bool(adset_ends) and all(e and _is_past(e) for e in adset_ends)

    async def _all_campaign_rows(
        self, account: str, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        """계정의 모든 캠페인 행 — 페이징을 끝까지 따라가 25개(기본 limit) 초과도 빠짐없이.

        Meta GET /campaigns는 기본 25개씩 페이지로 준다. cursors.after로 next가 없을 때까지 순회.
        include_archived=True면 보관(ARCHIVED, 삭제분 포함)도 effective_status 필터로 함께 받는다.
        (단 Ads Manager '임시 저장됨' 초안은 API가 반환하지 않아 게시 전엔 안 잡힌다.)
        """
        rows: list[dict[str, Any]] = []
        params: dict[str, Any] = {"fields": _CAMPAIGN_FIELDS, "limit": 100}
        if include_archived:
            # 기본은 ACTIVE/PAUSED만 — ARCHIVED 포함해야 삭제·보관 캠페인이 나온다.
            params["effective_status"] = _ARCHIVED_STATUSES
        while True:
            payload = await self._client.get(f"{account}/campaigns", params)
            rows.extend(payload.get("data", []))
            paging = payload.get("paging", {})
            after = (paging.get("cursors") or {}).get("after")
            if not after or not paging.get("next"):
                break
            params = {**params, "after": after}
        return rows

    async def list_campaigns(self, include_archived: bool = False) -> list[CampaignInfo]:
        """광고계정의 캠페인 목록 — 대시보드용(이름·상태·일예산).

        Meta ``GET /act_{id}/campaigns``. daily_budget은 캠페인 예산 최적화(CBO) 시에만
        캠페인 노드에 존재 — 광고세트 예산이면 광고세트 일예산 합으로 보완한다.
        include_archived=True면 보관/삭제(ARCHIVED) 캠페인도 포함('삭제됨' 표시·과거 데이터 조회용).
        """
        account = normalize_ad_account(self._client.ad_account_id)
        # 데모 핀이 있으면 보관분도 받아와야(핀 캠페인이 보관 상태일 수 있음) 고정 표시가 된다.
        fetch_archived = include_archived or bool(_DEMO_PINNED_CAMPAIGN_IDS)
        # 캠페인 목록(페이징 끝까지)·광고세트 정보 병렬 — 순차면 Meta 왕복이 직렬로 쌓임.
        rows, adset_info = await asyncio.gather(
            self._all_campaign_rows(account, fetch_archived),
            self._adset_info(account),
        )
        out: list[CampaignInfo] = []
        for row in rows:
            cid = str(row.get("id", ""))
            status = str(row.get("effective_status", "")).upper()
            info = adset_info.get(cid, {})
            ends = info.get("ends", [])
            campaign_stop = row.get("stop_time")
            # 표시용 종료일 — 캠페인 stop_time 우선, 없으면 광고세트 종료일 중 가장 늦은 것
            ended_at = campaign_stop or max([e for e in ends if e], default=None)
            # 캠페인(CBO) 예산 우선, 없으면(0) 광고세트 예산 합 — 일예산·총예산 각각.
            daily = _to_int(row.get("daily_budget")) or info.get("budget", 0)
            lifetime = _to_int(row.get("lifetime_budget")) or info.get("lifetime", 0)
            # 일예산 우선, 없으면 총예산, 둘 다 없으면 none(예산 미상 — '—'로 표시).
            if daily > 0:
                budget_type = "daily"
            elif lifetime > 0:
                budget_type = "lifetime"
            else:
                budget_type = "none"
            # 게재 기간이 끝났으면 effective_status가 ACTIVE라도 '종료'로 본다(충전해도 재개 안 됨).
            if self._schedule_ended(campaign_stop, ends):
                state = CampaignState.ENDED
            else:
                state = _STATE_MAP.get(status, CampaignState.DRAFT)
            # 데모 핀: 삭제/보관이라도 데이터와 함께 고정 표시하되 상태는 '종료됨'(실 게재 아님).
            # 핀 아닌 보관분은 토글(include_archived) 켤 때만 노출.
            if cid in _DEMO_PINNED_CAMPAIGN_IDS:
                state = CampaignState.ENDED
            elif status == "ARCHIVED" and not include_archived:
                continue
            out.append(
                CampaignInfo(
                    campaign_id=cid,
                    name=str(row.get("name", "")),
                    state=state,
                    daily_budget_krw=daily,
                    lifetime_budget_krw=lifetime,
                    budget_type=budget_type,
                    ended_at=ended_at,
                )
            )
        return out

    async def fetch_hourly_metrics(
        self,
        campaign_id: str,
        day: datetime,
        fault: object = None,  # noqa: ARG002 — Mock 시그니처 호환용(실데이터엔 무의미)
        daily_budget_krw: int = 0,  # noqa: ARG002 — 동상
    ) -> list[MetricsSnapshot]:
        """하루치 시간별 지표 — 감지 파이프라인 입력 형태(MockAdPlatform 호환).

        Meta hourly breakdown(24행)을 MetricsSnapshot 리스트로 매핑. reach/frequency는
        시간별 원천값을 그대로 싣고 cum_impressions만 러닝 합산(best-effort).
        """
        date = day.astimezone(UTC).date().isoformat()
        params = {
            "fields": _HOURLY_FIELDS,
            "level": "campaign",
            "time_range": json.dumps({"since": date, "until": date}),
            "breakdowns": "hourly_stats_aggregated_by_advertiser_time_zone",
        }
        payload = await self._client.get(f"{campaign_id}/insights", params)
        rows = payload.get("data") or []

        snapshots: list[MetricsSnapshot] = []
        cum_impressions = 0
        for row in rows:
            hour = _parse_hour(row.get("hourly_stats_aggregated_by_advertiser_time_zone"))
            impressions = _to_int(row.get("impressions"))
            cum_impressions += impressions
            snapshots.append(
                MetricsSnapshot(
                    campaign_id=campaign_id,
                    as_of=day.replace(hour=hour, minute=0, second=0, microsecond=0),
                    impressions=impressions,
                    clicks=_to_int(row.get("clicks")),
                    inline_link_clicks=_to_int(row.get("inline_link_clicks")),
                    spend_krw=_to_int(row.get("spend")),
                    cum_impressions=cum_impressions,
                    cum_reach=_to_int(row.get("reach")),
                    frequency=_to_float(row.get("frequency")),
                    ctr=_to_float(row.get("ctr")) / 100.0,
                    cpm_krw=_to_int(row.get("cpm")),
                    cpc_krw=_to_int(row.get("cpc")),
                )
            )
        return snapshots

    async def fetch_daily_metrics(self, campaign_id: str) -> list[dict]:
        """일자별 지출·노출 (lifetime, time_increment=1) — 종료·중단돼도 실제 운영 추이.

        시간별(오늘)과 달리 캠페인 전 기간을 일 단위로 받아, 멈춰 있어도 차트가 비지 않는다.
        """
        payload = await self._client.get(
            f"{campaign_id}/insights",
            {
                "fields": (
                    "spend,impressions,clicks,inline_link_clicks,reach,ctr,cpc,cpm,"
                    "actions,action_values,purchase_roas"
                ),
                "date_preset": "maximum",
                "time_increment": "1",
            },
        )
        out: list[dict] = []
        for row in payload.get("data", []):
            inline = _to_int(row.get("inline_link_clicks"))
            spend = _to_int(row.get("spend"))
            conv_count, conv_event = _count_conversions(row.get("actions"))
            conv = int(round(conv_count)) if conv_count is not None else None
            cvr = conv / inline if conv is not None and inline else (0.0 if conv == 0 else None)
            roas: float | None = None
            if conv_event == "purchase":
                value = _purchase_value(row.get("action_values"))
                roas = _purchase_value(row.get("purchase_roas"))
                if roas is None and value is not None:
                    roas = value / spend if spend else 0.0
            out.append(
                {
                    "label": str(row.get("date_start", ""))[5:],  # 'YYYY-MM-DD' → 'MM-DD'
                    "impressions": _to_int(row.get("impressions")),
                    "clicks": _to_int(row.get("clicks")),
                    "reach": _to_int(row.get("reach")),
                    "spend_krw": spend,
                    "ctr": _to_float(row.get("ctr")) / 100.0,  # Meta ctr 백분율 → 비율
                    "cpc_krw": _to_int(row.get("cpc")),
                    "cpm_krw": _to_int(row.get("cpm")),
                    "conversions": conv,
                    "cvr": cvr,
                    "roas": roas,
                }
            )
        return out

    async def get_campaign_targeting(self, campaign_id: str) -> dict:
        """캠페인 목표·광고세트 타겟팅·크리에이티브 — 시뮬레이터 사전 입력용.

        캠페인 노드에서 objective, 첫 광고세트에서 targeting(age_min/max·genders),
        첫 광고에서 headline·body·image_url을 가져온다.
        leads/conversion 광고는 title이 object_story_spec.link_data.name에 있어
        _CREATIVE_FIELDS_FULL로 확장해서 조회한다.
        """
        campaign_data, adset_data, ads_data = await asyncio.gather(
            self._client.get(campaign_id, {"fields": "objective,name"}),
            self._client.get(
                f"{campaign_id}/adsets",
                {"fields": "targeting", "limit": "1"},
            ),
            self._client.get(
                f"{campaign_id}/ads",
                {
                    "fields": (
                        "name,creative{image_url,thumbnail_url,title,body,"
                        "object_story_spec{link_data{name,message,picture},"
                        "photo_data{url}},"
                        "asset_feed_spec{images{url},bodies{text},titles{text}}}"
                    ),
                    "limit": "1",
                    "effective_status": _ARCHIVED_STATUSES,
                },
            ),
        )
        targeting = {}
        adsets = adset_data.get("data", [])
        if adsets:
            targeting = adsets[0].get("targeting") or {}
        genders_raw = targeting.get("genders") or []
        if genders_raw == [1]:
            gender = "M"
        elif genders_raw == [2]:
            gender = "F"
        else:
            gender = ""

        # 첫 광고 크리에이티브에서 headline·body·image 추출
        # 우선순위: creative.title → oss.link_data.name → asset_feed_spec.titles
        ad_headline: str | None = None
        ad_body: str | None = None
        ad_image_url: str | None = None
        ads = ads_data.get("data", [])
        if ads:
            creative = ads[0].get("creative") or {}
            oss = creative.get("object_story_spec") or {}
            link_data = oss.get("link_data") or {}
            afs = creative.get("asset_feed_spec") or {}

            ad_headline = (
                creative.get("title")
                or link_data.get("name")
                or ((afs.get("titles") or [{}])[0].get("text"))
            )
            ad_body = (
                creative.get("body")
                or link_data.get("message")
                or ((afs.get("bodies") or [{}])[0].get("text"))
            )
            ad_image_url = _pick_image(creative) or link_data.get("picture")

        # Advantage+ 등 광역 타겟팅은 age 제약 없음 → Meta 기본값(18~65)으로 폴백
        age_min = targeting.get("age_min") or 18
        age_max = targeting.get("age_max") or 65

        # 실제 소비자 수 — insights reach(도달) 기반.
        # leads는 actions 파싱이 필요하고 권한에 따라 누락 가능 → reach 1차 사용.
        # 실패해도 나머지 타겟팅 정보는 정상 반환.
        reach = 0
        leads = 0
        try:
            ins_data = await self._client.get(
                f"{campaign_id}/insights",
                {"fields": "reach,actions", "date_preset": "maximum"},
            )
            ins = (ins_data.get("data") or [{}])[0]
            reach = _to_int(ins.get("reach"))
            # leads: actions 배열에서 action_type이 lead 계열인 것 합산
            _lead_types = frozenset(
                {
                    "lead",
                    "onsite_conversion.lead_grouped",
                    "offsite_conversion.fb_pixel_lead",
                }
            )
            for act in ins.get("actions") or []:
                if act.get("action_type") in _lead_types:
                    leads += _to_int(act.get("value"))
        except Exception:
            pass

        if leads > 0:
            suggested_persona_count = min(200, max(10, leads))
        elif reach > 0:
            suggested_persona_count = min(200, max(10, reach))
        else:
            suggested_persona_count = 20

        # 광고 텍스트 기반 카테고리 추천
        cat_text = " ".join(filter(None, [campaign_data.get("name"), ad_headline, ad_body]))
        category_id, service_class = _guess_category(cat_text)

        return {
            "campaign_id": campaign_id,
            "campaign_name": campaign_data.get("name", ""),
            "objective": campaign_data.get("objective", ""),
            "age_min": age_min,
            "age_max": age_max,
            "gender": gender,
            "ad_headline": ad_headline,
            "ad_body": ad_body,
            "ad_image_url": ad_image_url,
            "category_id": category_id,
            "service_class": service_class,
            "suggested_persona_count": suggested_persona_count,
        }

    async def get_account_spend(self, date_preset: str = "this_month") -> int:
        """계정 단위 기간 소진(KRW) — 예산 페이싱의 '이번 달 소진'. 1콜로 합계."""
        account = normalize_ad_account(self._client.ad_account_id)
        payload = await self._client.get(
            f"{account}/insights", {"fields": "spend", "date_preset": date_preset}
        )
        rows = payload.get("data", [])
        return _to_int(rows[0].get("spend")) if rows else 0

    async def get_account_daily_spend(self, date_preset: str = "this_month") -> list[dict]:
        """계정 단위 일자별 소진 — 페이싱 곡선(계획 vs 실제)용. [{date, spend_krw}]."""
        account = normalize_ad_account(self._client.ad_account_id)
        payload = await self._client.get(
            f"{account}/insights",
            {"fields": "spend", "date_preset": date_preset, "time_increment": "1"},
        )
        return [
            {"date": str(r.get("date_start", "")), "spend_krw": _to_int(r.get("spend"))}
            for r in payload.get("data", [])
        ]
