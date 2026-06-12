"""Instagram 게시 어댑터 — Meta Graph API Content Publishing + Mock.

자격증명(META_ACCESS_TOKEN, META_IG_USER_ID)이 모두 있으면 실제 Graph API로 게시하고,
없으면 Mock으로 동작한다 (게시 절차 시뮬레이션 + 가짜 ID 반환).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Protocol

import httpx
from pydantic import BaseModel, Field

from core.config import settings

logger = logging.getLogger("clickme")

_CONTAINER_POLL_INTERVAL = 2.0
_CONTAINER_POLL_MAX = 5


class PublishOutcome(BaseModel):
    success: bool
    mocked: bool = False
    container_id: str | None = None
    media_id: str | None = None
    error: str | None = None
    raw: dict = Field(default_factory=dict)


class InstagramPublisher(Protocol):
    async def publish_image(self, image_url: str, caption: str) -> PublishOutcome: ...


class MetaGraphPublisher:
    """Meta Graph API Content Publishing — 컨테이너 생성 → 상태 폴링 → 게시."""

    def __init__(
        self,
        access_token: str,
        ig_user_id: str,
        api_version: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = access_token
        self._ig_user_id = ig_user_id
        self._base = f"https://graph.facebook.com/{api_version}"
        self._transport = transport  # 테스트용 httpx MockTransport 주입 지점

    async def publish_image(self, image_url: str, caption: str) -> PublishOutcome:
        raw: dict = {}
        try:
            async with httpx.AsyncClient(timeout=30.0, transport=self._transport) as client:
                # 1) 미디어 컨테이너 생성 — IG가 image_url을 동기 다운로드 (JPEG만 지원)
                create_res = await client.post(
                    f"{self._base}/{self._ig_user_id}/media",
                    data={
                        "image_url": image_url,
                        "caption": caption,
                        "access_token": self._token,
                    },
                )
                raw["create_container"] = create_res.json()
                create_res.raise_for_status()
                container_id = raw["create_container"]["id"]

                # 2) 컨테이너 처리 완료 대기
                for _ in range(_CONTAINER_POLL_MAX):
                    status_res = await client.get(
                        f"{self._base}/{container_id}",
                        params={"fields": "status_code", "access_token": self._token},
                    )
                    raw["container_status"] = status_res.json()
                    if raw["container_status"].get("status_code") == "FINISHED":
                        break
                    await asyncio.sleep(_CONTAINER_POLL_INTERVAL)

                # 3) 게시 실행
                publish_res = await client.post(
                    f"{self._base}/{self._ig_user_id}/media_publish",
                    data={"creation_id": container_id, "access_token": self._token},
                )
                raw["publish"] = publish_res.json()
                publish_res.raise_for_status()

                return PublishOutcome(
                    success=True,
                    container_id=container_id,
                    media_id=raw["publish"]["id"],
                    raw=raw,
                )
        except Exception as exc:
            logger.exception("Instagram 게시 실패")
            return PublishOutcome(success=False, error=str(exc), raw=raw)


class MockInstagramPublisher:
    """자격증명 없을 때의 Mock — 실제 게시 없이 절차를 시뮬레이션."""

    async def publish_image(self, image_url: str, caption: str) -> PublishOutcome:
        logger.info(
            "[MOCK] Instagram 게시 시뮬레이션: caption=%r image_url=%.80s...",
            caption[:50],
            image_url,
        )
        return PublishOutcome(
            success=True,
            mocked=True,
            container_id=f"mock-container-{uuid.uuid4().hex[:12]}",
            media_id=f"mock-media-{uuid.uuid4().hex[:12]}",
            raw={"mock": True, "image_url": image_url, "caption": caption},
        )


def build_publisher() -> InstagramPublisher:
    """자격증명 유무로 실제/Mock 어댑터 자동 선택."""
    if settings.meta_access_token and settings.meta_ig_user_id:
        return MetaGraphPublisher(
            access_token=settings.meta_access_token,
            ig_user_id=settings.meta_ig_user_id,
            api_version=settings.meta_graph_api_version,
        )
    return MockInstagramPublisher()
