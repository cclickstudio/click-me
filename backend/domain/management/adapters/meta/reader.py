"""🤝 Meta 읽기 어댑터 — Insights / delivery_estimate / 상태 조회 (AdPlatformReader 구현).

Graph API JSON → contracts Port 스키마 변환만 담당한다. 정책·진단 판단은 하지 않는다.
reader는 공동 소유(🅰 합의) — MetricsSnapshot 등 매핑 스키마의 스튜어드는 🅰이므로
필드 해석 변경 시 🅰 합의. import는 contracts·adapters.meta.client만 (경계 §5 유지).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from domain.management.adapters.meta.client import MetaClient, build_meta_client
from domain.management.contracts.enums import CampaignState
from domain.management.contracts.schemas import (
    CampaignConfig,
    DeliveryEstimate,
    MetricsSnapshot,
)

if TYPE_CHECKING:
    pass

#: Meta effective_status → contracts CampaignState 매핑 (미등록 값은 DRAFT 보수 처리).
_STATE_MAP: dict[str, CampaignState] = {
    "ACTIVE": CampaignState.ACTIVE,
    "PAUSED": CampaignState.PAUSED,
    "CAMPAIGN_PAUSED": CampaignState.PAUSED,
    "ADSET_PAUSED": CampaignState.PAUSED,
    "IN_PROCESS": CampaignState.UNDER_REVIEW,
    "PENDING_REVIEW": CampaignState.UNDER_REVIEW,
    "PENDING_BILLING_INFO": CampaignState.UNDER_REVIEW,
    "WITH_ISSUES": CampaignState.ACTIVE_PENDING_REVIEW,
    "DELETED": CampaignState.ENDED,
    "ARCHIVED": CampaignState.ENDED,
    "COMPLETED": CampaignState.ENDED,
}

#: 트래픽 목표(클릭) — v1 스코프 (§7). delivery_estimate optimization_goal.
_TRAFFIC_OPTIMIZATION_GOAL = "LINK_CLICKS"

_INSIGHTS_FIELDS = (
    "impressions,clicks,inline_link_clicks,spend,reach,frequency,ctr,cpm,cpc,date_stop"
)


def _to_int(value: Any) -> int:
    return int(round(float(value))) if value not in (None, "") else 0


def _to_float(value: Any) -> float:
    return float(value) if value not in (None, "") else 0.0


def _parse_date_utc(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    # Meta insights date_stop = 'YYYY-MM-DD' → 해당일 UTC 자정
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


class MetaAdsReader:
    """AdPlatformReader 구현 — wiring.py가 Port에 꽂는다."""

    def __init__(self, settings: object = None, *, client: MetaClient | None = None) -> None:
        self._client = client or build_meta_client(settings)

    async def get_metrics(self, campaign_id: str, since: datetime) -> MetricsSnapshot:
        payload = await self._client.get(
            f"{campaign_id}/insights",
            {"fields": _INSIGHTS_FIELDS, "time_increment": 1},
        )
        rows = payload.get("data", [])
        row: dict[str, Any] = rows[0] if rows else {}
        impressions = _to_int(row.get("impressions"))
        clicks = _to_int(row.get("clicks"))
        reach = _to_int(row.get("reach"))
        return MetricsSnapshot(
            campaign_id=campaign_id,
            as_of=_parse_date_utc(row.get("date_stop"), since),
            impressions=impressions,
            clicks=clicks,
            inline_link_clicks=_to_int(row.get("inline_link_clicks")),
            spend_krw=_to_int(row.get("spend")),  # 계정 통화 = KRW 전제 (정수)
            cum_impressions=impressions,  # 단일 스냅샷 — 누적은 호출자 책임
            cum_reach=reach,
            frequency=_to_float(row.get("frequency")),
            ctr=_to_float(row.get("ctr")) / 100.0,  # Meta ctr은 백분율 → 비율로 환산
            cpm_krw=_to_int(row.get("cpm")),
            cpc_krw=_to_int(row.get("cpc")),
        )

    async def get_estimate(self, config: CampaignConfig) -> DeliveryEstimate:
        account = config.ad_account_id or (self._client.ad_account_id or "")
        payload = await self._client.get(
            f"act_{account}/delivery_estimate",
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
