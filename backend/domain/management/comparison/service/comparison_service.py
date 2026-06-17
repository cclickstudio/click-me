# 🅰 오가닉↔광고 비교 유스케이스 — organic reader + ad reader 합성
"""오가닉 게시물(OrganicInsightsReader)과 광고 캠페인(AdPlatformReader.get_metrics)을
합쳐 LiftResult를 산출한다. 외부 호출은 두 reader에만 위임(어댑터 교체 가능)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.management.comparison.lift import compute_lift
from domain.management.comparison.schemas import PostInsights, PostType

if TYPE_CHECKING:
    from datetime import datetime

    from domain.management.comparison.ports import OrganicInsightsReader
    from domain.management.comparison.schemas import LiftResult
    from domain.management.contracts.platform import AdPlatformReader


class ComparisonService:
    """오가닉 게시물 vs 광고 집행 게시물 성과 비교."""

    def __init__(self, organic_reader: OrganicInsightsReader, ad_reader: AdPlatformReader) -> None:
        self._organic = organic_reader
        self._ad = ad_reader

    async def compare(self, organic_post_id: str, campaign_id: str, since: datetime) -> LiftResult:
        organic = await self._organic.get_post_insights(organic_post_id)
        snap = await self._ad.get_metrics(campaign_id, since)
        paid = PostInsights(
            post_id=campaign_id,
            post_type=PostType.PAID,
            as_of=snap.as_of,
            reach=snap.cum_reach,
            impressions=snap.cum_impressions,
            engagement=snap.clicks,
            clicks=snap.inline_link_clicks,
            spend_krw=snap.spend_krw,
        )
        return compute_lift(organic, paid)
