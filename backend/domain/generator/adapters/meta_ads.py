"""Meta Marketing API 어댑터 — 광고 캠페인 생성 (기본 PAUSED).

안전상 모든 캠페인·광고세트·광고는 PAUSED 상태로 생성한다.
실제 비용이 발생하려면 사용자가 Ads Manager에서 직접 활성화해야 한다.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Protocol

import httpx
from pydantic import BaseModel, Field

from core.config import settings

logger = logging.getLogger("clickme")


def _date_to_unix(date_str: str) -> int:
    return int(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


class AdsOutcome(BaseModel):
    success: bool
    mocked: bool = False
    campaign_id: str | None = None
    adset_id: str | None = None
    creative_id: str | None = None
    ad_id: str | None = None
    error: str | None = None
    raw: dict = Field(default_factory=dict)


class AdvertiseRequest(BaseModel):
    candidate_id: str
    budget: int = Field(ge=1000, description="일 예산 (원, 최소 1000)")
    objective: str = "OUTCOME_TRAFFIC"
    targeting: dict = Field(
        default_factory=lambda: {"age_min": 18, "age_max": 65, "genders": [], "countries": ["KR"]}
    )
    destination_url: str = "https://example.com"
    start_date: str  # YYYY-MM-DD
    end_date: str | None = None


class MetaAdsProtocol(Protocol):
    async def create_ad_campaign(
        self, image_url: str, copy: dict, req: AdvertiseRequest
    ) -> AdsOutcome: ...


class MetaMarketingPublisher:
    """Meta Marketing API — 5단계 PAUSED 캠페인 생성."""

    def __init__(
        self,
        ad_account_id: str,
        page_id: str,
        ig_account_id: str,
        access_token: str,
        api_version: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._act = f"act_{ad_account_id.removeprefix('act_')}"
        self._page_id = page_id
        self._ig_account_id = ig_account_id
        self._token = access_token
        self._base = f"https://graph.facebook.com/{api_version}"
        self._transport = transport

    async def create_ad_campaign(
        self, image_url: str, copy: dict, req: AdvertiseRequest
    ) -> AdsOutcome:
        raw: dict = {}
        try:
            async with httpx.AsyncClient(timeout=60.0, transport=self._transport) as client:
                # 1) adimages → image_hash
                img_res = await client.post(
                    f"{self._base}/{self._act}/adimages",
                    data={"url": image_url, "access_token": self._token},
                )
                raw["adimages"] = img_res.json()
                img_res.raise_for_status()
                image_hash = next(iter(raw["adimages"].get("images", {}).values()), {}).get("hash")
                if not image_hash:
                    return AdsOutcome(
                        success=False, error="이미지 해시를 가져오지 못했습니다.", raw=raw
                    )

                # 2) Campaign (PAUSED)
                headline = (copy.get("headline") or "Ad")[:40]
                camp_res = await client.post(
                    f"{self._base}/{self._act}/campaigns",
                    data={
                        "name": f"ClickMe_{headline}",
                        "objective": req.objective,
                        "status": "PAUSED",
                        "special_ad_categories": "[]",
                        "access_token": self._token,
                    },
                )
                raw["campaign"] = camp_res.json()
                camp_res.raise_for_status()
                campaign_id = raw["campaign"]["id"]

                # 3) Ad Set (PAUSED)
                targeting = {
                    "age_min": req.targeting.get("age_min", 18),
                    "age_max": req.targeting.get("age_max", 65),
                    "geo_locations": {"countries": req.targeting.get("countries", ["KR"])},
                }
                if req.targeting.get("genders"):
                    targeting["genders"] = req.targeting["genders"]

                adset_data: dict = {
                    "name": f"ClickMe_AdSet_{headline}",
                    "campaign_id": campaign_id,
                    "daily_budget": str(req.budget),
                    "billing_event": "IMPRESSIONS",
                    "optimization_goal": "REACH",
                    "targeting": json.dumps(targeting),
                    "start_time": str(_date_to_unix(req.start_date)),
                    "status": "PAUSED",
                    "access_token": self._token,
                }
                if req.end_date:
                    adset_data["end_time"] = str(_date_to_unix(req.end_date))

                adset_res = await client.post(f"{self._base}/{self._act}/adsets", data=adset_data)
                raw["adset"] = adset_res.json()
                adset_res.raise_for_status()
                adset_id = raw["adset"]["id"]

                # 4) Ad Creative
                creative_res = await client.post(
                    f"{self._base}/{self._act}/adcreatives",
                    data={
                        "name": f"ClickMe_Creative_{headline}",
                        "object_story_spec": json.dumps(
                            {
                                "page_id": self._page_id,
                                "instagram_actor_id": self._ig_account_id,
                                "link_data": {
                                    "message": copy.get("headline", ""),
                                    "link": req.destination_url,
                                    "image_hash": image_hash,
                                    "description": copy.get("benefit_text", ""),
                                    "call_to_action": {
                                        "type": "LEARN_MORE",
                                        "value": {"link": req.destination_url},
                                    },
                                },
                            }
                        ),
                        "access_token": self._token,
                    },
                )
                raw["creative"] = creative_res.json()
                creative_res.raise_for_status()
                creative_id = raw["creative"]["id"]

                # 5) Ad (PAUSED)
                ad_res = await client.post(
                    f"{self._base}/{self._act}/ads",
                    data={
                        "name": f"ClickMe_Ad_{headline}",
                        "adset_id": adset_id,
                        "creative": json.dumps({"creative_id": creative_id}),
                        "status": "PAUSED",
                        "access_token": self._token,
                    },
                )
                raw["ad"] = ad_res.json()
                ad_res.raise_for_status()
                ad_id = raw["ad"]["id"]

                return AdsOutcome(
                    success=True,
                    campaign_id=campaign_id,
                    adset_id=adset_id,
                    creative_id=creative_id,
                    ad_id=ad_id,
                    raw=raw,
                )
        except Exception as exc:
            logger.exception("Meta 광고 집행 실패")
            error = str(exc)
            for key in ("campaign", "adset", "creative", "ad", "adimages"):
                meta_err = (raw.get(key) or {}).get("error", {})
                if isinstance(meta_err, dict) and meta_err.get("message"):
                    error = meta_err["message"]
                    break
            return AdsOutcome(success=False, error=error, raw=raw)


class MockMetaAdsPublisher:
    """자격증명/예산 없을 때의 Mock — 실제 집행 없이 절차 시뮬레이션."""

    async def create_ad_campaign(
        self, image_url: str, copy: dict, req: AdvertiseRequest
    ) -> AdsOutcome:
        logger.info(
            "[MOCK] Meta 광고 집행 시뮬레이션: objective=%s budget=%d", req.objective, req.budget
        )
        return AdsOutcome(
            success=True,
            mocked=True,
            campaign_id=f"mock-campaign-{uuid.uuid4().hex[:12]}",
            adset_id=f"mock-adset-{uuid.uuid4().hex[:12]}",
            creative_id=f"mock-creative-{uuid.uuid4().hex[:12]}",
            ad_id=f"mock-ad-{uuid.uuid4().hex[:12]}",
            raw={"mock": True},
        )


def build_ads_publisher() -> MetaAdsProtocol:
    """자격증명 유무로 실제/Mock 어댑터 자동 선택."""
    required = (
        settings.meta_ad_account_id,
        settings.meta_page_id,
        settings.meta_instagram_account_id,
        settings.meta_access_token,
    )
    if all(required):
        logger.info(
            "MetaMarketing: 실제 광고 집행 모드 (act=%s)", str(settings.meta_ad_account_id)[:8]
        )
        return MetaMarketingPublisher(
            ad_account_id=settings.meta_ad_account_id,  # type: ignore[arg-type]
            page_id=settings.meta_page_id,  # type: ignore[arg-type]
            ig_account_id=settings.meta_instagram_account_id,  # type: ignore[arg-type]
            access_token=settings.meta_access_token,  # type: ignore[arg-type]
            api_version=settings.meta_graph_api_version,
        )
    logger.warning(
        "MetaMarketing: Mock 모드 — META_AD_ACCOUNT_ID·META_PAGE_ID·META_INSTAGRAM_ACCOUNT_ID·META_ACCESS_TOKEN 확인"
    )
    return MockMetaAdsPublisher()
