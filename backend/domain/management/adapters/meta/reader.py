# 🅰 Meta 읽기 어댑터 — Insights / delivery_estimate / 상태 조회 (ads_read 스코프)
"""AdPlatformReader 구현 — Graph API 실호출.

wiring.py 가 ``use_mock=False`` 일 때 Port에 꽂는다. contracts 외 의존 없음(§5).
spend/cpm/cpc 는 광고계정 통화가 KRW 라는 전제로 정수 KRW 로 매핑한다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from domain.management.adapters.meta.client import MetaClient
from domain.management.contracts.enums import CampaignState
from domain.management.contracts.schemas import (
    CampaignConfig,
    DeliveryEstimate,
    MetricsSnapshot,
)

# Meta insights 조회 필드 (성과 읽기 핵심)
_INSIGHT_FIELDS = "impressions,clicks,inline_link_clicks,spend,reach,frequency,ctr,cpm,cpc"

# Meta effective_status → 도메인 CampaignState (D2)
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
}


def _to_int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_hour(label: str | None) -> int:
    """'14:00:00 - 14:59:59' → 14 (hourly breakdown 라벨 파싱)."""
    try:
        return int(str(label).split(":", 1)[0])
    except (TypeError, ValueError):
        return 0


class MetaAdsReader:
    """읽기 Port 구현 — 🅰 감지·진단이 소비. 외부 호출은 MetaClient 단일 경로."""

    def __init__(self, settings: object, *, client: MetaClient | None = None) -> None:
        self._client = client or MetaClient(settings)

    async def get_metrics(self, campaign_id: str, since: datetime) -> MetricsSnapshot:
        """캠페인 누적 성과 (since~현재 집계)를 한 스냅샷으로 반환."""
        params = {
            "fields": _INSIGHT_FIELDS,
            "level": "campaign",
            "time_range": json.dumps(
                {
                    "since": since.astimezone(UTC).date().isoformat(),
                    "until": datetime.now(UTC).date().isoformat(),
                }
            ),
        }
        payload = await self._client.get(f"{campaign_id}/insights", params)
        rows = payload.get("data") or []
        row = rows[0] if rows else {}

        impressions = _to_int(row.get("impressions"))
        return MetricsSnapshot(
            campaign_id=campaign_id,
            as_of=datetime.now(UTC),
            impressions=impressions,
            clicks=_to_int(row.get("clicks")),
            inline_link_clicks=_to_int(row.get("inline_link_clicks")),
            spend_krw=_to_int(row.get("spend")),
            cum_impressions=impressions,  # since 집계 = 누적과 동일
            cum_reach=_to_int(row.get("reach")),
            frequency=_to_float(row.get("frequency")),
            ctr=_to_float(row.get("ctr")) / 100.0,  # Meta ctr=백분율 → 비율로 정규화
            cpm_krw=_to_int(row.get("cpm")),
            cpc_krw=_to_int(row.get("cpc")),
        )

    async def get_state(self, campaign_id: str) -> CampaignState:
        """캠페인 effective_status → 도메인 상태. 미지의 값은 DRAFT 보수 매핑."""
        payload = await self._client.get(campaign_id, {"fields": "effective_status,status"})
        status = payload.get("effective_status") or payload.get("status") or ""
        return _STATE_MAP.get(status, CampaignState.DRAFT)

    async def get_estimate(self, config: CampaignConfig) -> DeliveryEstimate:
        """delivery_estimate — 미래 도달 예측(forecast). v1 best-effort(traffic=LINK_CLICKS)."""
        params = {
            "optimization_goal": "LINK_CLICKS",  # objective=traffic 대응
            "targeting_spec": json.dumps(config.target_audience or {}),
        }
        payload = await self._client.get(f"{config.ad_account_id}/delivery_estimate", params)
        rows = payload.get("data") or []
        row = rows[0] if rows else {}

        mau = _to_int(row.get("estimate_mau"))
        return DeliveryEstimate(
            campaign_id=config.campaign_id,
            estimate_ready=bool(row.get("estimate_ready", False)),
            estimate_mau_lower=_to_int(row.get("estimate_mau_lower_bound")) or mau,
            estimate_mau_upper=_to_int(row.get("estimate_mau_upper_bound")) or mau,
            as_of=datetime.now(UTC),
        )

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
            "fields": _INSIGHT_FIELDS,
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
