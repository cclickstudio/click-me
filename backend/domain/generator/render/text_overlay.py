"""광고 이미지 텍스트 합성 — 모델이 만든 배경 위에 카피를 코드로 또렷하게 렌더링.

gpt-image-1이 한글을 직접 렌더하면 글자가 깨지므로, 배경/제품 이미지는 모델이 생성하고
헤드라인·서브카피·혜택·CTA는 Pillow로 템플릿 좌표(% → 픽셀)에 직접 그린다.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from core.config import BACKEND_ROOT, settings
from domain.generator.contracts.schemas import AdCopy
from domain.generator.contracts.templates import AdTemplate

_DEFAULT_FONT_DIR = BACKEND_ROOT / "assets" / "fonts"
_WHITE = (255, 255, 255, 255)
_PLATE = (0, 0, 0, 110)  # 가독성용 반투명 배경판
_STROKE = (0, 0, 0, 200)
_DEFAULT_BRAND = (49, 130, 246)  # #3182F6


def _font_dir() -> Path:
    return Path(settings.generator_font_dir) if settings.generator_font_dir else _DEFAULT_FONT_DIR


def _font_path(bold: bool) -> str:
    name = "Pretendard-Bold.otf" if bold else "Pretendard-Regular.otf"
    bundled = _font_dir() / name
    if bundled.exists():
        return str(bundled)
    # 시스템 폰트 폴백 (Windows malgun)
    win = Path("C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf")
    if win.exists():
        return str(win)
    raise FileNotFoundError("한글 폰트를 찾을 수 없습니다 (assets/fonts/Pretendard-*.otf).")


def _hex_to_rgb(value: str | None) -> tuple[int, int, int]:
    if not value:
        return _DEFAULT_BRAND
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    try:
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
    except (ValueError, IndexError):
        return _DEFAULT_BRAND


def _wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: float
) -> list[str]:
    """공백 우선, 한 단어가 폭을 넘으면 글자 단위로 줄바꿈 (한글 대응)."""
    lines: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=font) <= max_w:
                line = trial
                continue
            if line:
                lines.append(line)
            if draw.textlength(word, font=font) <= max_w:
                line = word
            else:  # 단어 자체가 폭 초과 → 글자 단위 분해
                chunk = ""
                for ch in word:
                    if not chunk or draw.textlength(chunk + ch, font=font) <= max_w:
                        chunk += ch
                    else:
                        lines.append(chunk)
                        chunk = ch
                line = chunk
        lines.append(line)
    return [ln for ln in lines if ln] or [text]


def _fit(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    box_w: float,
    box_h: float,
    max_size: int,
    min_size: int = 12,
) -> tuple[ImageFont.FreeTypeFont, list[str], float]:
    """박스 안에 들어가는 최대 폰트 크기를 찾아 (font, 줄들, 줄높이) 반환."""
    size = max(min_size, max_size)
    while size >= min_size:
        font = ImageFont.truetype(font_path, size)
        lines = _wrap_text(draw, text, font, box_w)
        asc, desc = font.getmetrics()
        line_h = (asc + desc) * 1.12
        fits_h = line_h * len(lines) <= box_h
        fits_w = all(draw.textlength(ln, font=font) <= box_w for ln in lines)
        if fits_h and fits_w:
            return font, lines, line_h
        size -= 2
    font = ImageFont.truetype(font_path, min_size)
    lines = _wrap_text(draw, text, font, box_w)
    asc, desc = font.getmetrics()
    return font, lines, (asc + desc) * 1.12


def _render_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    *,
    bold: bool,
    max_ratio: float,
) -> None:
    text = (text or "").strip()
    if not text:
        return
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    path = _font_path(bold)
    font, lines, line_h = _fit(draw, text, path, bw, bh, max_size=max(12, int(bh * max_ratio)))
    total_h = line_h * len(lines)
    ty = y0 + (bh - total_h) / 2

    pad = max(6, int(line_h * 0.18))
    widest = max(draw.textlength(ln, font=font) for ln in lines)
    cx = x0 + bw / 2
    draw.rounded_rectangle(
        [cx - widest / 2 - pad, ty - pad, cx + widest / 2 + pad, ty + total_h + pad],
        radius=pad,
        fill=_PLATE,
    )
    stroke = max(1, font.size // 22)
    for line in lines:
        lw = draw.textlength(line, font=font)
        draw.text(
            (cx - lw / 2, ty),
            line,
            font=font,
            fill=_WHITE,
            stroke_width=stroke,
            stroke_fill=_STROKE,
        )
        ty += line_h


def _render_cta(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    brand: tuple[int, int, int],
) -> None:
    text = (text or "").strip()
    if not text:
        return
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    path = _font_path(bold=True)
    font, lines, line_h = _fit(
        draw, text, path, int(bw * 0.82), int(bh * 0.7), max_size=int(bh * 0.5)
    )
    line = lines[0]
    tw = draw.textlength(line, font=font)

    pad_x, pad_y = int(bh * 0.45), int(bh * 0.22)
    btn_w = min(bw, tw + pad_x * 2)
    btn_h = min(bh, line_h + pad_y * 2)
    bx0 = x0 + (bw - btn_w) / 2
    by0 = y0 + (bh - btn_h) / 2
    draw.rounded_rectangle(
        [bx0, by0, bx0 + btn_w, by0 + btn_h], radius=btn_h / 2, fill=(*brand, 255)
    )
    draw.text((bx0 + (btn_w - tw) / 2, by0 + (btn_h - line_h) / 2), line, font=font, fill=_WHITE)


def _paste_logo(img: Image.Image, logo_png: bytes, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    logo = Image.open(io.BytesIO(logo_png)).convert("RGBA")
    logo.thumbnail((bw, bh))
    img.paste(logo, (x0 + (bw - logo.width) // 2, y0 + (bh - logo.height) // 2), logo)


def compose_ad_image(
    background_png: bytes,
    copy: AdCopy,
    template: AdTemplate,
    brand_color: str | None = None,
    logo_png: bytes | None = None,
) -> bytes:
    """배경 PNG에 카피를 합성한 최종 광고 PNG 바이트를 반환한다."""
    img = Image.open(io.BytesIO(background_png)).convert("RGBA")
    width, height = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    brand = _hex_to_rgb(brand_color)

    head_area = template.area_by_role("headline")
    if head_area:
        x0, y0, x1, y1 = head_area.pixel_box(width, height)
        if (copy.subcopy or "").strip():
            split = y0 + int((y1 - y0) * 0.62)
            _render_text(draw, copy.headline, (x0, y0, x1, split), bold=True, max_ratio=0.85)
            _render_text(draw, copy.subcopy, (x0, split, x1, y1), bold=False, max_ratio=0.7)
        else:
            _render_text(draw, copy.headline, (x0, y0, x1, y1), bold=True, max_ratio=0.85)

    ben_area = template.area_by_role("benefit")
    if ben_area:
        _render_text(
            draw, copy.benefit_text, ben_area.pixel_box(width, height), bold=True, max_ratio=0.8
        )

    cta_area = template.area_by_role("cta")
    if cta_area:
        _render_cta(draw, copy.cta, cta_area.pixel_box(width, height), brand)

    composed = Image.alpha_composite(img, overlay)

    if logo_png:
        logo_area = template.area_by_role("logo")
        if logo_area:
            _paste_logo(composed, logo_png, logo_area.pixel_box(width, height))

    out = io.BytesIO()
    composed.save(out, format="PNG")
    return out.getvalue()
