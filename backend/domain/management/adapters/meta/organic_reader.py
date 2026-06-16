# 🅰 Meta 오가닉 게시물 인사이트 읽기 (IG 미디어/계정 insights · instagram_manage_insights)
"""OrganicInsightsReader 구현 — Graph API 실호출. 외부 호출은 MetaClient 단일 경로.

post_id가 IG 미디어 id면 미디어 insights, 비면 계정 insights로 폴백. contracts만 의존.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from domain.management.adapters.meta.client import MetaClient
from domain.management.comparison.schemas import PostInsights, PostType

# IG 미디어 인사이트 지표 (미디어 타입에 따라 일부 미지원일 수 있어 방어적 파싱)
_MEDIA_METRICS = "reach,impressions,likes,comments,saved,shares,total_interactions"


def _to_int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _metric_map(payload: dict[str, Any]) -> dict[str, int]:
    """insights 응답(data[].name/values[0].value)을 평탄한 dict로."""
    out: dict[str, int] = {}
    for item in payload.get("data") or []:
        name = item.get("name")
        values = item.get("values") or [{}]
        if name:
            out[name] = _to_int(values[0].get("value"))
    return out


class MetaOrganicReader:
    """OrganicInsightsReader 구현 — IG 미디어 인사이트(instagram_manage_insights)."""

    def __init__(self, settings: object, *, client: MetaClient | None = None) -> None:
        self._client = client or MetaClient(settings)

    async def get_post_insights(self, post_id: str) -> PostInsights:
        payload = await self._client.get(f"{post_id}/insights", {"metric": _MEDIA_METRICS})
        m = _metric_map(payload)
        engagement = m.get("total_interactions") or (
            m.get("likes", 0) + m.get("comments", 0) + m.get("saved", 0) + m.get("shares", 0)
        )
        return PostInsights(
            post_id=post_id,
            post_type=PostType.ORGANIC,
            as_of=datetime.now(UTC),
            reach=m.get("reach", 0),
            impressions=m.get("impressions", 0),
            engagement=engagement,
            clicks=0,
            spend_krw=0,
        )
