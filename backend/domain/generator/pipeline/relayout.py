# 플랫폼별 리레이아웃 — base(텍스트 없는 이미지)를 LLM 재호출 없이 PIL로 다른 사이즈에 재구성
from __future__ import annotations

import io

from PIL import Image, ImageFilter, ImageOps

from domain.generator.contracts.enums import AdStrategy, TemplateType
from domain.generator.pipeline.image_generator import composite_logo
from domain.generator.pipeline.text_overlay import render_ad_text

# 플랫폼 → (가로, 세로) px
PLATFORM_SIZES: dict[str, tuple[int, int]] = {
    "ig_feed": (1080, 1080),
    "ig_story": (1080, 1920),
    "fb_feed": (1200, 628),
    "linkedin": (1200, 627),
}


def _blur_extend(base: Image.Image, tw: int, th: int) -> Image.Image:
    """base를 타깃 비율로 맞춤 — 제품은 비율 유지로 가운데 배치, 빈 공간은 블러 확장으로 채움.

    AI 재호출 없이 PIL만 사용하므로 제품 픽셀은 변형되지 않는다(비율 유지 스케일 + 패딩).
    """
    base = base.convert("RGB")
    # 배경: 타깃을 꽉 채우도록 cover 후 강하게 블러
    cover = ImageOps.fit(base, (tw, th), method=Image.LANCZOS)
    canvas = cover.filter(ImageFilter.GaussianBlur(radius=max(tw, th) // 30))
    # 전경: 비율 유지로 타깃 안에 contain → 가운데 배치(왜곡·잘림 없음)
    fit = base.copy()
    fit.thumbnail((tw, th), Image.LANCZOS)
    canvas.paste(fit, ((tw - fit.width) // 2, (th - fit.height) // 2))
    return canvas


def render_platform(
    base_bytes: bytes,
    *,
    headline: str,
    body: str,
    cta: str,
    template: TemplateType,
    platform: str,
    brand_color: str | None = None,
    logo_bytes: bytes | None = None,
    strategy: AdStrategy | None = None,
) -> bytes:
    """텍스트 없는 base를 지정 플랫폼 사이즈로 리레이아웃해 최종 PNG bytes를 반환한다."""
    if platform not in PLATFORM_SIZES:
        raise ValueError(f"지원하지 않는 플랫폼: {platform!r}")
    tw, th = PLATFORM_SIZES[platform]

    canvas = _blur_extend(Image.open(io.BytesIO(base_bytes)), tw, th)
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")

    out = render_ad_text(
        buf.getvalue(),
        headline=headline,
        body=body,
        cta=cta,
        template=template,
        brand_color=brand_color,
        strategy=strategy,
    )
    if logo_bytes is not None:
        out = composite_logo(out, logo_bytes, template)
    return out
