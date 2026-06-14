from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from domain.generator.contracts.enums import TemplateType
from domain.generator.contracts.schemas import ImageAnalysis

_FONTS_DIR = Path(__file__).parents[3] / "assets" / "fonts"


# ── 폰트 ──────────────────────────────────────────────────────────────────────


def _find_font(bold: bool = False) -> str | None:
    name_bold = "NotoSansKR-Bold.ttf"
    name_regular = "NotoSansKR-Regular.ttf"
    candidates = [
        _FONTS_DIR / (name_bold if bold else name_regular),
        Path("C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf"),
        Path(
            "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Bold.otf"
            if bold
            else "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf"
        ),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _find_font(bold)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _luminance(rgb: tuple[int, int, int]) -> float:
    return (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    """Character-level wrapping — safe for Korean."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for char in paragraph:
            test = line + char
            if draw.textbbox((0, 0), test, font=font)[2] > max_width and line:
                lines.append(line)
                line = char
            else:
                line = test
        if line:
            lines.append(line)
    return lines or [""]


# ── 오버레이 ──────────────────────────────────────────────────────────────────


def _gradient_overlay(
    canvas: Image.Image,
    x: int,
    y: int,
    w: int,
    h: int,
    color: tuple[int, int, int] = (0, 0, 0),
    alpha_start: int = 0,
    alpha_end: int = 220,
) -> None:
    """위→아래 선형 그라디언트 오버레이."""
    steps = min(h, 512)
    col = Image.new("RGBA", (1, steps))
    px = col.load()
    for i in range(steps):
        a = int(alpha_start + (alpha_end - alpha_start) * i / max(steps - 1, 1))
        px[0, i] = (*color, a)
    gradient = col.resize((w, h), Image.NEAREST)
    canvas.alpha_composite(gradient, (x, y))


def _solid_overlay(canvas: Image.Image, x: int, y: int, w: int, h: int, alpha: int = 170) -> None:
    block = Image.new("RGBA", (w, h), (0, 0, 0, alpha))
    canvas.alpha_composite(block, (x, y))


def _draw_pill_scrim(
    canvas: Image.Image,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    alpha: int = 150,
    radius: int = 20,
) -> None:
    """반투명 pill 스크림을 alpha_composite로 합성."""
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=(0, 0, 0, alpha))
    canvas.alpha_composite(layer)


def _scrim_alpha(brightness: str) -> int:
    """이미지 밝기에 따라 스크림 불투명도 반환."""
    return {"dark": 115, "medium": 155, "light": 195}.get(brightness, 155)


# ── 텍스트 드로잉 ─────────────────────────────────────────────────────────────


def _draw_centered_lines(
    canvas: Image.Image,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    area_x: int,
    area_w: int,
    y: int,
    color: tuple[int, int, int],
    line_gap: int = 8,
    shadow: bool = False,
) -> int:
    draw = ImageDraw.Draw(canvas)
    positions: list[tuple[int, int, int, int]] = []
    cur_y = y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = area_x + (area_w - tw) // 2
        positions.append((x, cur_y, tw, th))
        cur_y += th + line_gap

    if shadow:
        shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        for line, (x, sy, _, _) in zip(lines, positions, strict=False):
            shadow_draw.text((x + 3, sy + 4), line, font=font, fill=(0, 0, 0, 160))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(6))
        canvas.alpha_composite(shadow_layer)
        draw = ImageDraw.Draw(canvas)

    for line, (x, sy, _, _) in zip(lines, positions, strict=False):
        draw.text((x, sy), line, font=font, fill=color)
    return cur_y


def _draw_left_lines(
    canvas: Image.Image,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    x: int,
    y: int,
    color: tuple[int, int, int],
    line_gap: int = 8,
    shadow: bool = False,
) -> int:
    draw = ImageDraw.Draw(canvas)
    positions: list[tuple[int, int]] = []
    cur_y = y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        th = bbox[3] - bbox[1]
        positions.append((cur_y, th))
        cur_y += th + line_gap

    if shadow:
        shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        for line, (sy, _) in zip(lines, positions, strict=False):
            shadow_draw.text((x + 3, sy + 4), line, font=font, fill=(0, 0, 0, 160))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(6))
        canvas.alpha_composite(shadow_layer)
        draw = ImageDraw.Draw(canvas)

    for line, (sy, _) in zip(lines, positions, strict=False):
        draw.text((x, sy), line, font=font, fill=color)
        y = sy
    return cur_y


def _draw_cta_button(
    draw: ImageDraw.ImageDraw,
    cta: str,
    font: ImageFont.FreeTypeFont,
    x_center: int,
    y: int,
    bg_rgb: tuple[int, int, int],
    text_color: tuple[int, int, int] = (255, 255, 255),
    pad_x: int = 36,
    pad_y: int = 16,
) -> None:
    bbox = draw.textbbox((0, 0), cta, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x1 = x_center - tw // 2 - pad_x
    y1 = y - pad_y
    x2 = x_center + tw // 2 + pad_x
    y2 = y + th + pad_y

    if _luminance(bg_rgb) > 0.72:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=14, fill=bg_rgb)
        draw.rounded_rectangle([x1, y1, x2, y2], radius=14, outline=(50, 50, 50), width=2)
        eff_text = text_color if _luminance(text_color) < 0.55 else (30, 30, 30)
        draw.text((x_center - tw // 2, y), cta, font=font, fill=eff_text)
    else:
        draw.rounded_rectangle([x1 + 3, y1 + 3, x2 + 3, y2 + 3], radius=14, fill=(10, 10, 10))
        draw.rounded_rectangle([x1, y1, x2, y2], radius=14, fill=bg_rgb)
        draw.text((x_center - tw // 2, y), cta, font=font, fill=text_color)


# ── Template layouts ──────────────────────────────────────────────────────────


def _compose_template_a(
    canvas: Image.Image,
    w: int,
    h: int,
    headline: str,
    body: str,
    cta: str,
    cta_rgb: tuple[int, int, int],
    brightness: str = "medium",
) -> None:
    """제품 강조: 이미지 하단으로 자연스럽게 페이드되는 그라디언트 오버레이."""
    scrim_a = _scrim_alpha(brightness)

    # 그라디언트 구간을 넓혀 자연스러운 전환
    _gradient_overlay(canvas, 0, int(h * 0.30), w, int(h * 0.32), alpha_start=0, alpha_end=120)
    # 텍스트 존 보장: 밝기에 따라 적응형 alpha
    _solid_overlay(canvas, 0, int(h * 0.57), w, h - int(h * 0.57), alpha=scrim_a)

    draw = ImageDraw.Draw(canvas)
    margin = int(w * 0.08)
    text_w = w - margin * 2
    base = min(w, h)

    hl_font = _load_font(max(36, int(base * 0.050)), bold=True)
    bd_font = _load_font(max(20, int(base * 0.028)), bold=False)
    ct_font = _load_font(max(22, int(base * 0.030)), bold=True)

    hl_y = int(h * 0.60)

    # 브랜드 컬러 포인트 라인
    accent_w = int(w * 0.10)
    accent_y = hl_y - int(h * 0.038)
    draw.rectangle(
        [w // 2 - accent_w // 2, accent_y, w // 2 + accent_w // 2, accent_y + 4],
        fill=cta_rgb,
    )

    hl_y = _draw_centered_lines(
        canvas,
        _wrap_text(headline, hl_font, text_w, draw),
        hl_font,
        margin,
        text_w,
        hl_y,
        (255, 255, 255),
        8,
        shadow=True,
    )

    hl_y += int(h * 0.022)
    _draw_centered_lines(
        canvas,
        _wrap_text(body, bd_font, text_w, draw),
        bd_font,
        margin,
        text_w,
        hl_y,
        (210, 220, 235),
        6,
    )

    _draw_cta_button(draw, cta, ct_font, w // 2, h - int(h * 0.095), cta_rgb)


def _compose_template_b(
    canvas: Image.Image,
    w: int,
    h: int,
    headline: str,
    body: str,
    cta: str,
    cta_rgb: tuple[int, int, int],
    brightness: str = "medium",
) -> None:
    """이벤트 강조: 헤드라인 pill 스크림 + 하단 그라디언트."""
    scrim_a = _scrim_alpha(brightness)

    bottom_grad_y = int(h * 0.64)
    bottom_grad_h = h - bottom_grad_y

    base = min(w, h)
    margin = int(w * 0.07)
    text_w = w - margin * 2

    hl_font = _load_font(max(32, int(base * 0.046)), bold=True)
    bd_font = _load_font(max(22, int(base * 0.031)), bold=False)
    ct_font = _load_font(max(24, int(base * 0.033)), bold=True)

    # 하단 그라디언트 + 솔리드 (기존 유지)
    _gradient_overlay(canvas, 0, int(h * 0.46), w, int(h * 0.22), alpha_start=0, alpha_end=140)
    _solid_overlay(canvas, 0, bottom_grad_y, w, bottom_grad_h, alpha=scrim_a + 20)

    draw = ImageDraw.Draw(canvas)
    hl_lines = _wrap_text(headline, hl_font, text_w, draw)

    # 헤드라인 텍스트 바운딩 박스 계산
    line_widths: list[int] = []
    line_heights: list[int] = []
    for line in hl_lines:
        bbox = draw.textbbox((0, 0), line, font=hl_font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])
    total_hl_h = sum(line_heights) + 8 * (len(hl_lines) - 1)
    max_line_w = max(line_widths) if line_widths else int(text_w * 0.6)

    pill_pad_x = int(w * 0.06)
    pill_pad_y = int(h * 0.022)
    hl_y = int(h * 0.09)

    pill_x1 = w // 2 - max_line_w // 2 - pill_pad_x
    pill_y1 = hl_y - pill_pad_y
    pill_x2 = w // 2 + max_line_w // 2 + pill_pad_x
    pill_y2 = hl_y + total_hl_h + pill_pad_y

    # pill 위에 브랜드 컬러 액센트 라인
    accent_cx = w // 2
    accent_half = int(w * 0.05)
    draw.rectangle(
        [accent_cx - accent_half, pill_y1 - 8, accent_cx + accent_half, pill_y1 - 4],
        fill=cta_rgb,
    )

    # 반투명 pill 스크림
    _draw_pill_scrim(canvas, pill_x1, pill_y1, pill_x2, pill_y2, alpha=scrim_a + 25, radius=20)

    # 헤드라인 텍스트 (쉐도우 없이 — pill이 대비 보장)
    _draw_centered_lines(
        canvas, hl_lines, hl_font, margin, text_w, hl_y, (255, 255, 255), 8, shadow=False
    )

    # 하단: 본문 + CTA
    inner_pad = int(bottom_grad_h * 0.22)
    y = bottom_grad_y + inner_pad
    bd_lines = _wrap_text(body, bd_font, text_w, draw)
    y = _draw_centered_lines(canvas, bd_lines, bd_font, margin, text_w, y, (225, 232, 245), 8)
    y += int(bottom_grad_h * 0.16)
    _draw_cta_button(draw, cta, ct_font, w // 2, y, cta_rgb)


def _compose_template_c(
    canvas: Image.Image,
    w: int,
    h: int,
    headline: str,
    body: str,
    cta: str,
    cta_rgb: tuple[int, int, int],
    brightness: str = "medium",
) -> None:
    """브랜드 강조: 좌측 반투명 브랜드 패널 + 우측 제품 이미지."""
    scrim_a = _scrim_alpha(brightness)
    panel_w = int(w * 0.42)

    base = min(w, h)
    margin = int(panel_w * 0.12)
    text_w = panel_w - margin * 2

    hl_font = _load_font(max(28, int(base * 0.040)), bold=True)
    bd_font = _load_font(max(17, int(base * 0.025)), bold=False)
    ct_font = _load_font(max(20, int(base * 0.028)), bold=True)
    label_font = _load_font(max(12, int(base * 0.016)), bold=False)

    # 좌측 패널: alpha_composite로 배경이 살짝 비치도록
    panel_color = cta_rgb if _luminance(cta_rgb) < 0.72 else (30, 40, 80)
    panel_alpha = max(210, min(235, scrim_a + 80))

    panel_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel_layer)
    panel_draw.rectangle([0, 0, panel_w, h], fill=(*panel_color, panel_alpha))
    # 패널 우측 하이라이트 라인 (약간 밝은 패널 색)
    light = tuple(min(255, c + 35) for c in panel_color)
    panel_draw.rectangle([panel_w - 3, 0, panel_w, h], fill=(*light, 255))
    canvas.alpha_composite(panel_layer)

    draw = ImageDraw.Draw(canvas)

    # AD 레이블
    draw.text((margin, int(h * 0.07)), "AD", font=label_font, fill=(200, 200, 200))

    # 헤드라인
    y = int(h * 0.18)
    y = _draw_left_lines(
        canvas,
        _wrap_text(headline, hl_font, text_w, draw),
        hl_font,
        margin,
        y,
        (255, 255, 255),
        10,
        shadow=False,
    )

    # 구분선
    y += int(h * 0.04)
    sep_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sep_layer).line([(margin, y), (margin + text_w, y)], fill=(255, 255, 255, 70), width=1)
    canvas.alpha_composite(sep_layer)
    y += int(h * 0.04)

    draw = ImageDraw.Draw(canvas)

    # 본문
    _draw_left_lines(
        canvas,
        _wrap_text(body, bd_font, text_w, draw),
        bd_font,
        margin,
        y,
        (220, 228, 245),
        7,
    )

    # CTA 버튼: 흰 배경 + 패널 컬러 텍스트
    cta_y = h - int(h * 0.13)
    draw = ImageDraw.Draw(canvas)
    bbox = draw.textbbox((0, 0), cta, font=ct_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 32, 14
    bx1 = panel_w // 2 - tw // 2 - pad_x
    by1 = cta_y - pad_y
    bx2 = panel_w // 2 + tw // 2 + pad_x
    by2 = cta_y + th + pad_y

    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow_layer).rounded_rectangle(
        [bx1 + 3, by1 + 3, bx2 + 3, by2 + 3], radius=14, fill=(0, 0, 0, 60)
    )
    canvas.alpha_composite(shadow_layer)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=14, fill=(255, 255, 255))
    draw.text((panel_w // 2 - tw // 2, cta_y), cta, font=ct_font, fill=panel_color)


# ── Public API ────────────────────────────────────────────────────────────────


def composite_text(
    bg_bytes: bytes,
    headline: str,
    body: str,
    cta: str,
    template: TemplateType,
    brand_color: str | None = None,
    image_analysis: ImageAnalysis | None = None,
) -> bytes:
    canvas = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
    w, h = canvas.size

    cta_rgb = _hex_to_rgb(brand_color) if brand_color else (49, 130, 246)
    brightness = image_analysis.brightness if image_analysis else "medium"

    if template == TemplateType.A:
        _compose_template_a(canvas, w, h, headline, body, cta, cta_rgb, brightness)
    elif template == TemplateType.B:
        _compose_template_b(canvas, w, h, headline, body, cta, cta_rgb, brightness)
    else:
        _compose_template_c(canvas, w, h, headline, body, cta, cta_rgb, brightness)

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
