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
from domain.management.contracts.enums import CampaignState
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
    "ARCHIVED": CampaignState.ENDED,
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

# 캠페인 목록 조회 필드 — 대시보드 목록(이름·상태·일예산·종료일). daily_budget은 KRW(offset=1) 전제.
# stop_time: Meta는 게재 기간이 끝나도 effective_status를 ACTIVE로 유지 → 종료 판별에 필요.
_CAMPAIGN_FIELDS = "id,name,effective_status,daily_budget,stop_time"

# 광고세트 예산·종료일 조회 필드 — 캠페인 노드에 예산/종료일이 없을 때(광고세트 일정) 보완.
_ADSET_FIELDS = "daily_budget,campaign_id,end_time"

# 플랫폼별 분해 조회 필드 — publisher_platform breakdown (FB/IG 등)
_PLATFORM_FIELDS = "impressions,clicks,spend,reach"

# 연령×성별 분해 조회 필드 — age,gender breakdown
_DEMOGRAPHIC_FIELDS = "impressions,clicks,spend,reach"

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


# 계정 자금·게재 가능 조회 필드 — 선불 잔액 소진·계정 비활성 감지
_FUNDING_FIELDS = "account_status,disable_reason,funding_source_details"

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


def _to_int(value: Any) -> int:
    return int(round(float(value))) if value not in (None, "") else 0


def _to_float(value: Any) -> float:
    return float(value) if value not in (None, "") else 0.0


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

    async def get_metrics(self, campaign_id: str, since: datetime) -> MetricsSnapshot:
        # lifetime(date_preset=maximum)으로 누적 집계행 1개를 받는다 — 캠페인이 종료·게재중단돼도
        # "오늘" 윈도우면 0이 되므로, 실제 누적 성과를 그대로 보여주려 전체 기간으로 조회한다.
        # (since는 date_stop 없을 때 as_of 폴백으로만 사용)
        payload = await self._client.get(
            f"{campaign_id}/insights",
            {
                "fields": _INSIGHTS_FIELDS,
                "date_preset": "maximum",
            },
        )
        rows = payload.get("data", [])
        row: dict[str, Any] = rows[0] if rows else {}
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
        """캠페인 대표 크리에이티브 — 산하 광고의 이름·썸네일(중첩 creative 필드)."""
        payload = await self._client.get(
            f"{campaign_id}/ads",
            {"fields": _CREATIVE_FIELDS, "limit": _CREATIVE_LIMIT},
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
        return AccountFunding(
            account_status=account_status,
            available_balance_krw=available,
            delivery_blocked=blocked,
            block_reason=reason,
        )

    async def _adset_info(self, account: str) -> dict[str, dict[str, Any]]:
        """캠페인별 광고세트 일예산 합 + 종료일 목록 — 캠페인 노드 정보 보완용.

        반환: ``{campaign_id: {"budget": int, "ends": [end_time | None, ...]}}``.
        budget은 캠페인 노드에 예산이 없을 때(광고세트 예산), ends는 캠페인 stop_time이
        없을 때 게재 기간 종료 판별에 쓴다.
        """
        payload = await self._client.get(f"{account}/adsets", {"fields": _ADSET_FIELDS})
        info: dict[str, dict[str, Any]] = {}
        for row in payload.get("data", []):
            cid = str(row.get("campaign_id", ""))
            if not cid:
                continue
            entry = info.setdefault(cid, {"budget": 0, "ends": []})
            entry["budget"] += _to_int(row.get("daily_budget"))  # KRW offset=1
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

    async def list_campaigns(self) -> list[CampaignInfo]:
        """광고계정의 캠페인 목록 — 대시보드용(이름·상태·일예산).

        Meta ``GET /act_{id}/campaigns``. daily_budget은 캠페인 예산 최적화(CBO) 시에만
        캠페인 노드에 존재 — 광고세트 예산이면 광고세트 일예산 합으로 보완한다.
        """
        account = normalize_ad_account(self._client.ad_account_id)
        # 캠페인 목록·광고세트 정보 병렬 — 순차면 Meta 왕복 2번이 직렬로 쌓임.
        payload, adset_info = await asyncio.gather(
            self._client.get(f"{account}/campaigns", {"fields": _CAMPAIGN_FIELDS}),
            self._adset_info(account),
        )
        rows = payload.get("data", [])
        out: list[CampaignInfo] = []
        for row in rows:
            cid = str(row.get("id", ""))
            status = str(row.get("effective_status", "")).upper()
            info = adset_info.get(cid, {})
            # 캠페인(CBO) 예산 우선, 없으면(0) 광고세트 일예산 합
            budget = _to_int(row.get("daily_budget")) or info.get("budget", 0)
            # 게재 기간이 끝났으면 effective_status가 ACTIVE라도 '종료'로 본다(충전해도 재개 안 됨).
            if self._schedule_ended(row.get("stop_time"), info.get("ends", [])):
                state = CampaignState.ENDED
            else:
                state = _STATE_MAP.get(status, CampaignState.DRAFT)
            out.append(
                CampaignInfo(
                    campaign_id=cid,
                    name=str(row.get("name", "")),
                    state=state,
                    daily_budget_krw=budget,
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
