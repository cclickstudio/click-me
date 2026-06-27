# Gemini 멀티모달 생성기 단위 테스트 — 이미지+카피 파싱 / 상품 입력 분기 (실 API 호출 없음)
import pytest

import domain.generator.pipeline.multimodal_generator as mg
from domain.generator.contracts.enums import AdSize, AdStrategy, TemplateType
from domain.generator.contracts.pipeline_schemas import ProductAnalysis


def _product() -> ProductAnalysis:
    return ProductAnalysis(
        product_name="테스트 상품",
        core_values=["신뢰"],
        pain_points=["불편"],
        benefits=["편리함"],
        target_audience="20대",
        objective="conversion",
    )


# ── google.genai 응답 구조 대역 ────────────────────────────────────────────────
class _Inline:
    def __init__(self, data: bytes):
        self.data = data


class _Part:
    def __init__(self, *, image: bytes | None = None, text: str | None = None):
        self.inline_data = _Inline(image) if image is not None else None
        self.text = text


class _Content:
    def __init__(self, parts):
        self.parts = parts


class _Candidate:
    def __init__(self, parts):
        self.content = _Content(parts)


class _Response:
    def __init__(self, parts):
        self.candidates = [_Candidate(parts)] if parts is not None else []
        self.usage_metadata = None  # _record_genai_usage 대비 (트레이싱 off면 미사용)


class _Models:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _Aio:
    def __init__(self, models):
        self.models = models


class _Client:
    def __init__(self, response):
        self.models = _Models(response)
        self.aio = _Aio(self.models)


class _FakeGenai:
    """genai 모듈 대역 — Client() 호출 시 고정 response를 내는 클라이언트 반환."""

    def __init__(self, response):
        self._response = response
        self.client: _Client | None = None

    def Client(self, **kwargs):  # noqa: N802 — genai SDK API명(genai.Client) 모방
        self.client = _Client(self._response)
        return self.client


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    # 재시도 백오프 sleep을 즉시 통과시켜 테스트 지연 제거
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(mg.asyncio, "sleep", _noop)


@pytest.fixture
def patch_genai(monkeypatch):
    def _apply(parts) -> _FakeGenai:
        fake = _FakeGenai(_Response(parts))
        monkeypatch.setattr(mg, "genai", fake)
        return fake

    return _apply


# ── 이미지+카피 파싱 ────────────────────────────────────────────────────────────
async def test_parses_image_and_copy(patch_genai):
    parts = [
        _Part(image=b"PNGBYTES"),
        _Part(text='여기 카피입니다 {"headline": "헤드", "body": "본문", "cta": "지금"}'),
    ]
    patch_genai(parts)
    img, copy = await mg.generate_image_and_copy(
        _product(), AdStrategy.BENEFIT, TemplateType.A, size=AdSize.SQUARE
    )
    assert img == b"PNGBYTES"
    assert (copy.headline, copy.body, copy.cta) == ("헤드", "본문", "지금")


async def test_missing_copy_json_uses_default_cta(patch_genai):
    parts = [_Part(image=b"img"), _Part(text="설명만 있고 JSON 없음")]
    patch_genai(parts)
    img, copy = await mg.generate_image_and_copy(_product(), AdStrategy.BENEFIT, TemplateType.A)
    assert img == b"img"
    assert copy.headline == ""
    assert copy.cta == "지금 바로 확인하기"  # JSON 없을 때 기본 CTA


# ── 상품 이미지 멀티모달 입력 분기 ──────────────────────────────────────────────
async def test_without_product_sends_prompt_only(patch_genai):
    fake = patch_genai([_Part(image=b"img"), _Part(text="{}")])
    await mg.generate_image_and_copy(_product(), AdStrategy.BENEFIT, TemplateType.A)
    contents = fake.client.models.calls[-1]["contents"]
    assert len(contents) == 1  # 프롬프트(텍스트)만


async def test_with_product_appends_image_input(patch_genai):
    fake = patch_genai([_Part(image=b"img"), _Part(text="{}")])
    await mg.generate_image_and_copy(
        _product(), AdStrategy.BENEFIT, TemplateType.A, product_image_bytes=b"PRODUCT"
    )
    contents = fake.client.models.calls[-1]["contents"]
    assert len(contents) == 2  # 프롬프트 + 상품 이미지 part


# ── 이미지 누락 시 실패 ─────────────────────────────────────────────────────────
async def test_raises_when_no_image(patch_genai):
    patch_genai([_Part(text='{"headline": "x", "body": "y", "cta": "z"}')])
    with pytest.raises(RuntimeError):
        await mg.generate_image_and_copy(_product(), AdStrategy.BENEFIT, TemplateType.A)


async def test_raises_when_no_candidates(patch_genai):
    patch_genai(None)
    with pytest.raises(RuntimeError):
        await mg.generate_image_and_copy(_product(), AdStrategy.BENEFIT, TemplateType.A)
