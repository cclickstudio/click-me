from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from domain.generator.contracts.enums import TemplateType
from domain.generator.contracts.pipeline_schemas import ImageAnalysis

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
    """Word-aware wrapping with character-level fallback for long single words."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        line = ""
        for word in words:
            test = (line + " " + word).strip() if line else word
            if draw.textbbox((0, 0), test, font=font)[2] > max_width:
                if line:
                    lines.append(line)
                    line = word
                else:
                    # single word too long — character-level fallback
                    for char in word:
                        test_char = line + char
                        if draw.textbbox((0, 0), test_char, font=font)[2] > max_width and line:
                            lines.append(line)
                            line = char
                        else:
                            line = test_char
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
    stroke_width: int = 0,
    stroke_color: tuple[int, int, int] = (0, 0, 0),
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
        if stroke_width > 0:
            draw.text(
                (x, sy),
                line,
                font=font,
                fill=color,
                stroke_width=stroke_width,
                stroke_fill=stroke_color,
            )
        else:
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

    # bbox[1] is typically negative (font ascender offset); compensate so text is
    # visually centered — without this the upper padding is visibly smaller than lower.
    tx = x_center - tw // 2 - bbox[0]
    ty = y - bbox[1]

    if _luminance(bg_rgb) > 0.72:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=14, fill=bg_rgb)
        draw.rounded_rectangle([x1, y1, x2, y2], radius=14, outline=(50, 50, 50), width=2)
        eff_text = text_color if _luminance(text_color) < 0.55 else (30, 30, 30)
        draw.text((tx, ty), cta, font=font, fill=eff_text)
    else:
        draw.rounded_rectangle([x1 + 3, y1 + 3, x2 + 3, y2 + 3], radius=14, fill=(10, 10, 10))
        draw.rounded_rectangle([x1, y1, x2, y2], radius=14, fill=bg_rgb)
        draw.text((tx, ty), cta, font=font, fill=text_color)


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

    # 굵은 선 제거: 그라디언트 끝 alpha == solid 시작 alpha 로 맞춰 경계선 소멸
    grad_start_a = int(h * 0.30)
    grad_h_a = int(h * 0.30)
    solid_y_a = grad_start_a + grad_h_a
    _gradient_overlay(canvas, 0, grad_start_a, w, grad_h_a, alpha_start=0, alpha_end=scrim_a)
    _solid_overlay(canvas, 0, solid_y_a, w, h - solid_y_a, alpha=scrim_a)

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
    """이벤트 강조: 헤드라인 스트로크 텍스트 + 하단 그라디언트."""
    scrim_a = _scrim_alpha(brightness)

    # 굵은 선 제거: 그라디언트 끝 alpha == solid 시작 alpha 로 맞춰 경계선 소멸
    grad_start_b = int(h * 0.44)
    grad_h_b = int(h * 0.22)
    bottom_grad_y = grad_start_b + grad_h_b
    bottom_grad_h = h - bottom_grad_y
    _gradient_overlay(canvas, 0, grad_start_b, w, grad_h_b, alpha_start=0, alpha_end=scrim_a + 20)
    _solid_overlay(canvas, 0, bottom_grad_y, w, bottom_grad_h, alpha=scrim_a + 20)

    base = min(w, h)
    margin = int(w * 0.07)
    text_w = w - margin * 2

    hl_font = _load_font(max(32, int(base * 0.046)), bold=True)
    bd_font = _load_font(max(22, int(base * 0.031)), bold=False)
    ct_font = _load_font(max(24, int(base * 0.033)), bold=True)

    draw = ImageDraw.Draw(canvas)
    hl_lines = _wrap_text(headline, hl_font, text_w, draw)

    # pill 스크림·액센트 라인 제거 → 흰색 글자 + 검정 스트로크로 대체
    hl_y = int(h * 0.09)
    _draw_centered_lines(
        canvas,
        hl_lines,
        hl_font,
        margin,
        text_w,
        hl_y,
        (255, 255, 255),
        8,
        shadow=False,
        stroke_width=4,
        stroke_color=(0, 0, 0),
    )

    # 하단: 본문 + CTA
    inner_pad = int(bottom_grad_h * 0.22)
    y = bottom_grad_y + inner_pad
    bd_lines = _wrap_text(body, bd_font, text_w, draw)
    y = _draw_centered_lines(canvas, bd_lines, bd_font, margin, text_w, y, (225, 232, 245), 8)
    y += int(bottom_grad_h * 0.16)
    _draw_cta_button(draw, cta, ct_font, w // 2, y, cta_rgb)


def _horizontal_gradient_panel(
    canvas: Image.Image,
    panel_w: int,
    h: int,
    color: tuple[int, int, int],
    alpha_full: int,
    fade_ratio: float = 0.28,
    x_offset: int = 0,
) -> None:
    """좌측 불투명 → 우측 투명 그라디언트 패널. x_offset으로 시작 위치 지정 가능."""
    alpha_col = Image.new("L", (panel_w, 1))
    fade_start = int(panel_w * (1.0 - fade_ratio))
    for x in range(panel_w):
        if x <= fade_start:
            a = alpha_full
        else:
            t = (x - fade_start) / max(panel_w - fade_start, 1)
            a = int(alpha_full * (1.0 - t))
        alpha_col.putpixel((x, 0), a)
    alpha_map = alpha_col.resize((panel_w, h), Image.BILINEAR)

    panel_rgb = Image.new("RGB", (panel_w, h), color)
    r, g, b = panel_rgb.split()
    panel_rgba = Image.merge("RGBA", (r, g, b, alpha_map))

    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(panel_rgba, (x_offset, 0))
    canvas.alpha_composite(layer)


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
    """브랜드 강조: 좌측 솔리드 텍스트 패널 + 그라데이션 전환 구간 + 우측 제품 영역."""
    scrim_a = _scrim_alpha(brightness)
    panel_w = int(w * 0.46)  # 텍스트 전용 솔리드 구간
    gradient_ext = int(w * 0.07)  # 솔리드 구간 이후 그라데이션 전환 폭

    margin = int(panel_w * 0.10)
    text_w = panel_w - margin * 2

    # 폰트 크기는 패널 폭 기준 — 전체 이미지 크기로 계산하면 패널 대비 너무 커짐
    hl_font = _load_font(max(22, int(panel_w * 0.068)), bold=True)
    bd_font = _load_font(max(14, int(panel_w * 0.040)), bold=False)
    ct_font = _load_font(max(16, int(panel_w * 0.046)), bold=True)
    label_font = _load_font(max(11, int(panel_w * 0.026)), bold=False)

    panel_color = cta_rgb if _luminance(cta_rgb) < 0.72 else (30, 40, 80)
    panel_alpha = max(210, min(235, scrim_a + 80))

    # 솔리드 패널 (텍스트 영역 전체가 불투명 배경 위에 놓임)
    solid = Image.new("RGBA", (panel_w, h), (*panel_color, panel_alpha))
    canvas.alpha_composite(solid, (0, 0))

    # 그라데이션 구간: 솔리드 끝 → 완전 투명 (제품이 서서히 드러남)
    _horizontal_gradient_panel(
        canvas,
        gradient_ext,
        h,
        panel_color,
        panel_alpha,
        fade_ratio=1.0,
        x_offset=panel_w,
    )

    draw = ImageDraw.Draw(canvas)

    # AD 레이블
    draw.text((margin, int(h * 0.07)), "AD", font=label_font, fill=(200, 200, 200))

    # 헤드라인
    y = int(h * 0.18)
    y = _draw_centered_lines(
        canvas,
        _wrap_text(headline, hl_font, text_w, draw),
        hl_font,
        margin,
        text_w,
        y,
        (255, 255, 255),
        10,
        shadow=False,
    )

    # 구분선
    y += int(h * 0.04)
    sep_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sep_layer).line(
        [(margin, y), (margin + text_w, y)], fill=(255, 255, 255, 70), width=1
    )
    canvas.alpha_composite(sep_layer)
    y += int(h * 0.04)

    draw = ImageDraw.Draw(canvas)

    # 본문
    _draw_centered_lines(
        canvas,
        _wrap_text(body, bd_font, text_w, draw),
        bd_font,
        margin,
        text_w,
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
    # Compensate for font ascender offset so text is visually centered in button
    cta_bbox = draw.textbbox((0, 0), cta, font=ct_font)
    draw.text(
        (panel_w // 2 - tw // 2 - cta_bbox[0], cta_y - cta_bbox[1]),
        cta,
        font=ct_font,
        fill=panel_color,
    )


# ── Public API ────────────────────────────────────────────────────────────────


def _paste_logo(canvas: Image.Image, logo_png: bytes, w: int, h: int) -> None:
    """브랜드 로고를 좌상단에 합성 (텍스트 존과 겹치지 않는 안전 영역)."""
    try:
        logo = Image.open(io.BytesIO(logo_png)).convert("RGBA")
    except Exception:
        return
    box = max(48, int(min(w, h) * 0.13))
    logo.thumbnail((box, box), Image.LANCZOS)
    margin = int(min(w, h) * 0.045)
    canvas.alpha_composite(logo, (margin, margin))


def resize_to_target(img_bytes: bytes, width: int, height: int) -> bytes:
    """생성 이미지를 목표 치수로 맞춤 — 목표 종횡비로 center-crop 후 resize.

    gpt-image-1은 1024/1536만 생성하므로 1080 계열 출력은 이 단계에서 보정한다.
    """
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    sw, sh = img.size
    if (sw, sh) == (width, height):
        return img_bytes

    target_ratio = width / height
    src_ratio = sw / sh
    if src_ratio > target_ratio:  # 원본이 더 넓음 → 좌우 크롭
        new_w = round(sh * target_ratio)
        left = (sw - new_w) // 2
        img = img.crop((left, 0, left + new_w, sh))
    elif src_ratio < target_ratio:  # 원본이 더 높음 → 상하 크롭
        new_h = round(sw / target_ratio)
        top = (sh - new_h) // 2
        img = img.crop((0, top, sw, top + new_h))

    img = img.resize((width, height), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def composite_text(
    bg_bytes: bytes,
    headline: str,
    body: str,
    cta: str,
    template: TemplateType,
    brand_color: str | None = None,
    image_analysis: ImageAnalysis | None = None,
    logo_png: bytes | None = None,
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

    if logo_png:
        _paste_logo(canvas, logo_png, w, h)

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
