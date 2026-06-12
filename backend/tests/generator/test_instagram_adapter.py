"""Instagram 어댑터 테스트 — Mock 모드, 어댑터 자동 선택, Graph API 절차(httpx 모킹)."""

import httpx

from domain.generator.adapters.instagram import (
    MetaGraphPublisher,
    MockInstagramPublisher,
    build_publisher,
)
from domain.generator.service.generator_service import png_to_jpeg


async def test_mock_publisher_returns_fake_ids():
    outcome = await MockInstagramPublisher().publish_image("https://example.com/a.jpg", "캡션")
    assert outcome.success
    assert outcome.mocked
    assert outcome.media_id.startswith("mock-media-")
    assert outcome.raw["caption"] == "캡션"


def test_build_publisher_mock_without_credentials(monkeypatch):
    monkeypatch.setattr(
        "domain.generator.adapters.instagram.dotenv_values",
        lambda _: {"META_ACCESS_TOKEN": "", "META_IG_USER_ID": ""},
    )
    assert isinstance(build_publisher(), MockInstagramPublisher)


def test_build_publisher_real_with_credentials(monkeypatch):
    monkeypatch.setattr(
        "domain.generator.adapters.instagram.dotenv_values",
        lambda _: {"META_ACCESS_TOKEN": "token", "META_IG_USER_ID": "1789"},
    )
    assert isinstance(build_publisher(), MetaGraphPublisher)


async def test_meta_graph_publisher_flow():
    """컨테이너 생성 → 상태 폴링(FINISHED) → media_publish 순서 검증."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(f"{request.method} {path}")
        if request.method == "POST" and path.endswith("/1789/media"):
            return httpx.Response(200, json={"id": "container-1"})
        if request.method == "GET" and path.endswith("/container-1"):
            return httpx.Response(200, json={"status_code": "FINISHED", "id": "container-1"})
        if request.method == "POST" and path.endswith("/media_publish"):
            return httpx.Response(200, json={"id": "media-9"})
        return httpx.Response(404, json={"error": "unexpected"})

    publisher = MetaGraphPublisher(
        access_token="token",
        ig_user_id="1789",
        api_version="v21.0",
        transport=httpx.MockTransport(handler),
    )
    outcome = await publisher.publish_image("https://example.com/ad.jpg", "여름 신제품")

    assert outcome.success
    assert not outcome.mocked
    assert outcome.container_id == "container-1"
    assert outcome.media_id == "media-9"
    assert calls == [
        "POST /v21.0/1789/media",
        "GET /v21.0/container-1",
        "POST /v21.0/1789/media_publish",
    ]


async def test_meta_graph_publisher_failure_is_captured():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Invalid token"}})

    publisher = MetaGraphPublisher(
        access_token="bad",
        ig_user_id="1789",
        api_version="v21.0",
        transport=httpx.MockTransport(handler),
    )
    outcome = await publisher.publish_image("https://example.com/ad.jpg", "캡션")
    assert not outcome.success
    assert outcome.error
    assert "create_container" in outcome.raw  # 실패 시점까지의 응답 기록


def test_png_to_jpeg_conversion():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (10, 10), (49, 130, 246, 255)).save(buf, format="PNG")
    jpeg = png_to_jpeg(buf.getvalue())
    assert jpeg[:2] == b"\xff\xd8"  # JPEG SOI 마커
