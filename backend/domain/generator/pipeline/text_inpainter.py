import base64
import io
import logging

from langsmith import traceable
from openai import AsyncOpenAI, OpenAIError
from PIL import Image, ImageDraw

from core.config import settings
from domain.generator.contracts.enums import TemplateType
from domain.generator.contracts.pipeline_schemas import ImageAnalysis

logger = logging.getLogger("clickme")
_client = AsyncOpenAI(timeout=settings.generator_image_timeout)


def _create_mask(w: int, h: int, template: TemplateType) -> bytes:
    """투명(alpha=0) = AI가 채울 영역 / 불투명(alpha=255) = 유지할 영역."""
    mask = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(mask)

    if template == TemplateType.A:
        draw.rectangle([0, int(h * 0.58), w, h], fill=(0, 0, 0, 0))
    elif template == TemplateType.B:
        draw.rectangle([0, 0, w, int(h * 0.18)], fill=(0, 0, 0, 0))
        draw.rectangle([0, int(h * 0.72), w, h], fill=(0, 0, 0, 0))
    else:  # C
        draw.rectangle([0, 0, int(w * 0.42), h], fill=(0, 0, 0, 0))

    buf = io.BytesIO()
    mask.save(buf, format="PNG")
    return buf.getvalue()


def _build_prompt(
    template: TemplateType,
    image_analysis: ImageAnalysis,
    brand_color: str | None,
) -> str:
    mood = image_analysis.mood
    color_hint = f" Primary accent color: {brand_color}." if brand_color else ""

    if template == TemplateType.A:
        return (
            f"Extend this {mood} product photograph into a cinematic dark gradient zone. "
            f"The transition must be photorealistic and seamless — "
            f"shadows and lighting flow naturally downward from the product. "
            f"Result: a rich, deep dark area at the bottom "
            f"that feels like part of the original photo. "
            f"Absolutely no text, no UI elements. "
            f"Pure photographic quality.{color_hint}"
        )
    elif template == TemplateType.B:
        return (
            f"Fill the top band with a sleek solid brand panel "
            f"and the bottom band with a cinematic dark gradient "
            f"that fades naturally from this {mood} product shot. "
            f"Both bands must look like intentional photographic design, not overlays. "
            f"No text. No UI elements.{color_hint}"
        )
    else:  # C
        return (
            f"Fill the left panel with a deep, rich solid color panel "
            f"that transitions into a natural vignette where it meets the product on the right. "
            f"The panel should feel like part of the original {mood} composition, not pasted on. "
            f"No text. No UI elements.{color_hint}"
        )


@traceable(name="TextInpainter", metadata={"pipeline": "generator"})
async def inpaint_text_zone(
    bg_bytes: bytes,
    template: TemplateType,
    image_analysis: ImageAnalysis,
    brand_color: str | None = None,
) -> bytes:
    """AI로 텍스트 존을 사진처럼 자연스럽게 디자인. 실패·미지원 시 원본 반환."""
    if settings.generator_image_edit_provider != "openai":
        # 현재 이미지 편집은 openai만 구현 — 그 외 프로바이더는 원본 유지(파이프라인 비중단)
        logger.warning(
            "이미지 편집 미지원 프로바이더(%s) — 인페인팅 건너뜀",
            settings.generator_image_edit_provider,
        )
        return bg_bytes
    try:
        img = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
        w, h = img.size

        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        img_buf.seek(0)

        mask_buf = io.BytesIO(_create_mask(w, h, template))
        prompt = _build_prompt(template, image_analysis, brand_color)

        response = await _client.images.edit(
            model=settings.generator_image_edit_model,
            image=img_buf,
            mask=mask_buf,
            prompt=prompt,
            n=1,
        )

        return base64.b64decode(response.data[0].b64_json)

    except OpenAIError:
        return bg_bytes
