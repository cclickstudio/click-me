# 이미지 provider 디스패처 단위 테스트 — provider 라우팅 + gemini 미지원 검증 (실 API 호출 없음)
import base64

import pytest

from domain.generator.contracts.enums import AdSize
from domain.generator.pipeline import image_providers as ip


class _FakeData:
    def __init__(self, b64: str):
        self.b64_json = b64


class _FakeResp:
    def __init__(self, b64: str):
        self.data = [_FakeData(b64)]


class _FakeImages:
    """openai images 클라이언트 대역 — 호출 인자만 기록하고 고정 이미지 반환."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def edit(self, **kwargs):
        self.calls.append(("edit", kwargs))
        return _FakeResp(base64.b64encode(b"img").decode())

    async def generate(self, **kwargs):
        self.calls.append(("generate", kwargs))
        return _FakeResp(base64.b64encode(b"img").decode())


class _FakeClient:
    def __init__(self):
        self.images = _FakeImages()


@pytest.fixture
def fake_openai(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(ip, "_openai_client", client)
    return client


# ── gemini/미지원 provider는 거부 (config 훅 + OpenAI만 구현 설계) ──────────────
async def test_edit_rejects_non_openai():
    with pytest.raises(NotImplementedError):
        await ip.edit(b"x", "p", AdSize.SQUARE, provider="google_genai", model="m")


async def test_edit_with_mask_rejects_non_openai():
    with pytest.raises(NotImplementedError):
        await ip.edit_with_mask(b"b", b"m", "p", AdSize.SQUARE, provider="google_genai", model="m")


async def test_remove_background_rejects_non_openai():
    with pytest.raises(NotImplementedError):
        await ip.remove_background(b"x", provider="google_genai", model="m", quality="low")


async def test_generate_rejects_unknown_provider():
    with pytest.raises(NotImplementedError):
        await ip.generate("p", AdSize.SQUARE, provider="cohere", model="m", quality="low")


# ── generate provider 라우팅 ──────────────────────────────────────────────────
async def test_generate_routes_openai(monkeypatch):
    called = {}

    async def fake(prompt, size, model, quality):
        called["args"] = (prompt, size, model, quality)
        return b"openai"

    monkeypatch.setattr(ip, "_openai_generate", fake)
    out = await ip.generate(
        "p", AdSize.SQUARE, provider="openai", model="gpt-image-1", quality="low"
    )
    assert out == b"openai"
    assert called["args"] == ("p", AdSize.SQUARE, "gpt-image-1", "low")


async def test_generate_routes_google_genai(monkeypatch):
    called = {}

    async def fake(prompt, size, model):
        called["args"] = (prompt, size, model)
        return b"genai"

    monkeypatch.setattr(ip, "_genai_generate", fake)
    out = await ip.generate(
        "p", AdSize.SQUARE, provider="google_genai", model="gemini-2.5-flash-image", quality="low"
    )
    assert out == b"genai"
    assert called["args"] == ("p", AdSize.SQUARE, "gemini-2.5-flash-image")


# ── openai 호출 인자 검증 ──────────────────────────────────────────────────────
async def test_edit_with_mask_passes_mask(fake_openai):
    out = await ip.edit_with_mask(
        b"base", b"mask", "p", AdSize.SQUARE, provider="openai", model="gpt-image-1"
    )
    assert out == b"img"
    name, kwargs = fake_openai.images.calls[-1]
    assert name == "edit"
    assert kwargs["model"] == "gpt-image-1"
    assert kwargs.get("mask") is not None
    assert kwargs["size"] == AdSize.SQUARE.value


async def test_remove_background_transparent_omits_quality_for_gpt_image(fake_openai):
    await ip.remove_background(b"x", provider="openai", model="gpt-image-1", quality="low")
    _, kwargs = fake_openai.images.calls[-1]
    assert kwargs["background"] == "transparent"
    assert "quality" not in kwargs  # gpt-image 계열은 quality 미전달


async def test_remove_background_passes_quality_for_non_gpt_image(fake_openai):
    await ip.remove_background(b"x", provider="openai", model="dall-e-2", quality="low")
    _, kwargs = fake_openai.images.calls[-1]
    assert kwargs.get("quality") == "low"


async def test_openai_generate_gpt_image_omits_response_format(fake_openai):
    await ip.generate("p", AdSize.SQUARE, provider="openai", model="gpt-image-1", quality="medium")
    name, kwargs = fake_openai.images.calls[-1]
    assert name == "generate"
    assert "response_format" not in kwargs
    assert "quality" not in kwargs


async def test_openai_generate_non_gpt_image_adds_response_format(fake_openai):
    await ip.generate("p", AdSize.SQUARE, provider="openai", model="dall-e-3", quality="high")
    _, kwargs = fake_openai.images.calls[-1]
    assert kwargs["response_format"] == "b64_json"
    assert kwargs["quality"] == "high"
