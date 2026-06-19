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
    DeliveryEstimate,
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

# 캠페인 목록 조회 필드 — 대시보드 목록(이름·상태·일예산). daily_budget은 KRW(offset=1) 전제.
_CAMPAIGN_FIELDS = "id,name,effective_status,daily_budget"

# 광고세트 예산 조회 필드 — 캠페인 노드에 예산이 없을 때(광고세트 예산) 일예산 보완.
_ADSET_FIELDS = "daily_budget,campaign_id"

# 플랫폼별 분해 조회 필드 — publisher_platform breakdown (FB/IG 등)
_PLATFORM_FIELDS = "impressions,clicks,spend,reach"

# 계정 자금·게재 가능 조회 필드 — 선불 잔액 소진·계정 비활성 감지
_FUNDING_FIELDS = "account_status,disable_reason,funding_source_details"

_PURCHASE_ACTION_TYPES = (
    "offsite_conversion.fb_pixel_purchase",
    "omni_purchase",
    "purchase",
)


def _to_int(value: Any) -> int:
    return int(round(float(value))) if value not in (None, "") else 0


def _to_float(value: Any) -> float:
    return float(value) if value not in (None, "") else 0.0


def _extract_won(text: str) -> int | None:
    """'사용 가능한 잔액(₩5,000 KRW)' → 5000. 못 찾으면 None."""
    m = re.search(r"₩\s*([\d,]+)", text)
    return int(m.group(1).replace(",", "")) if m else None


def _purchase_metric(items: Any) -> float | None:
    """Meta action 배열에서 구매 값을 하나만 고른다.

    omni_purchase와 pixel_purchase가 동시에 내려오는 경우 같은 구매가 중복될 수 있어
    합산하지 않고 명시한 우선순위의 첫 값을 사용한다.
    """
    if not isinstance(items, list):
        return None
    values = {
        str(item.get("action_type")): _to_float(item.get("value"))
        for item in items
        if isinstance(item, dict)
    }
    for action_type in _PURCHASE_ACTION_TYPES:
        if action_type in values:
            return values[action_type]
    return 0.0


def _parse_date_utc(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    # Meta insights date_stop = 'YYYY-MM-DD' → 해당일 UTC 자정
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


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
        purchase_count = _purchase_metric(row.get("actions"))
        purchase_value = _purchase_metric(row.get("action_values"))
        meta_roas = _purchase_metric(row.get("purchase_roas"))
        conversions = int(round(purchase_count)) if purchase_count is not None else None
        purchase_value_krw = int(round(purchase_value)) if purchase_value is not None else None
        cvr = (
            conversions / inline_link_clicks
            if conversions is not None and inline_link_clicks
            else (0.0 if conversions == 0 else None)
        )
        roas = meta_roas
        if roas is None and purchase_value_krw is not None:
            roas = purchase_value_krw / spend_krw if spend_krw else 0.0
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
        payload = await self._client.get(campaign_id, {"fields": "effective_status"})
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

    async def _adset_daily_budgets(self, account: str) -> dict[str, int]:
        """캠페인별 광고세트 일예산 합 — 캠페인 노드에 예산이 없을 때(광고세트 예산) 보완."""
        payload = await self._client.get(f"{account}/adsets", {"fields": _ADSET_FIELDS})
        sums: dict[str, int] = {}
        for row in payload.get("data", []):
            cid = str(row.get("campaign_id", ""))
            if cid:
                sums[cid] = sums.get(cid, 0) + _to_int(row.get("daily_budget"))  # KRW offset=1
        return sums

    async def list_campaigns(self) -> list[CampaignInfo]:
        """광고계정의 캠페인 목록 — 대시보드용(이름·상태·일예산).

        Meta ``GET /act_{id}/campaigns``. daily_budget은 캠페인 예산 최적화(CBO) 시에만
        캠페인 노드에 존재 — 광고세트 예산이면 광고세트 일예산 합으로 보완한다.
        """
        account = normalize_ad_account(self._client.ad_account_id)
        # 캠페인 목록·광고세트 예산 병렬 — 순차면 Meta 왕복 2번이 직렬로 쌓임.
        payload, adset_budgets = await asyncio.gather(
            self._client.get(f"{account}/campaigns", {"fields": _CAMPAIGN_FIELDS}),
            self._adset_daily_budgets(account),
        )
        rows = payload.get("data", [])
        out: list[CampaignInfo] = []
        for row in rows:
            cid = str(row.get("id", ""))
            status = str(row.get("effective_status", "")).upper()
            # 캠페인(CBO) 예산 우선, 없으면(0) 광고세트 일예산 합
            budget = _to_int(row.get("daily_budget")) or adset_budgets.get(cid, 0)
            out.append(
                CampaignInfo(
                    campaign_id=cid,
                    name=str(row.get("name", "")),
                    state=_STATE_MAP.get(status, CampaignState.DRAFT),
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
