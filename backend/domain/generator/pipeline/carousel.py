# 캐러셀 슬라이드 렌더 — 공통 배경에 슬라이드 카피(PIL) + 슬라이드 번호/예시 배지
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from domain.generator.contracts.enums import TemplateType
from domain.generator.pipeline.carousel_copy import CarouselSlide
from domain.generator.pipeline.text_overlay import _FONT_BOLD, render_ad_text

_WHITE = (255, 255, 255, 255)


def _badge(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
) -> None:
    tw = int(draw.textlength(text, font=font))
    ascent, descent = font.getmetrics()
    th = ascent + descent
    pad = int(th * 0.4)
    draw.rounded_rectangle(
        [x, y, x + tw + 2 * pad, y + th + pad], radius=(th + pad) // 2, fill=fill
    )
    draw.text((x + pad, y + pad // 2), text, font=font, fill=_WHITE)


def render_carousel_slide(
    bg_bytes: bytes,
    slide: CarouselSlide,
    idx: int,
    total: int,
    brand_color: str | None = None,
) -> bytes:
    """공통 배경에 슬라이드 카피를 PIL로 얹고, 슬라이드 번호/예시 배지를 그린다."""
    out = render_ad_text(
        bg_bytes,
        headline=slide.headline,
        body=slide.body,
        cta=slide.cta or "",
        template=TemplateType.A,
        brand_color=brand_color,
    )
    img = Image.open(io.BytesIO(out)).convert("RGBA")
    w, h = img.size
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(_FONT_BOLD, max(16, h // 40))

    # 슬라이드 번호(좌상단)
    _badge(draw, int(w * 0.04), int(h * 0.04), f"{idx}/{total}", font, (0, 0, 0, 140))

    # 후기(예시) 배지(우상단)
    if "후기" in slide.role or "예시" in slide.role:
        text = "예시"
        tw = int(draw.textlength(text, font=font))
        ascent, descent = font.getmetrics()
        pad = int((ascent + descent) * 0.4)
        bw = tw + 2 * pad
        _badge(draw, w - int(w * 0.04) - bw, int(h * 0.04), text, font, (230, 120, 20, 220))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
