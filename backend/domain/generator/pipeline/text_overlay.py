# 광고 카피(헤드라인·본문·CTA)를 PIL로 직접 렌더링 — 확산모델 텍스트 잘림·오탈자 방지
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from domain.generator.contracts.enums import AdStrategy, TemplateType
from domain.generator.pipeline.style_profile import get_style

_FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"
_FONT_BOLD = str(_FONT_DIR / "Pretendard-Bold.otf")
_FONT_REGULAR = str(_FONT_DIR / "Pretendard-Regular.otf")
# 감성형 얇은 폰트 — 있으면 Light, 없으면 Regular로 폴백(나중에 .otf만 넣으면 자동 적용).
_FONT_LIGHT_PATH = _FONT_DIR / "Pretendard-Light.otf"
_FONT_LIGHT = str(_FONT_LIGHT_PATH) if _FONT_LIGHT_PATH.exists() else _FONT_REGULAR

_DEFAULT_ACCENT = (37, 99, 235)  # brand_color 없을 때 기본 강조색(파랑)
_WHITE = (255, 255, 255, 255)
_LIGHT = (235, 235, 235, 255)
_GOLD = (245, 180, 40, 255)  # 별점 골드
_INK = (34, 34, 34, 255)  # 리뷰 카드 본문 다크
_GRAY = (110, 110, 110, 255)  # 리뷰 카드 보조 텍스트

# 숫자 토큰(할인율·수량·기간 등) — 단어에 숫자가 포함되면 강조 대상으로 본다.
_NUM_RE = re.compile(r"\d")


def _contrast_stroke(color: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """텍스트 색의 밝기에 따라 대비되는 외곽선 색을 고른다(패널 없는 floating/emotional 가독성)."""
    r, g, b = color[:3]
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return (255, 255, 255, 230) if luminance < 140 else (0, 0, 0, 200)


@dataclass(frozen=True)
class _Block:
    """텍스트 블록 — box는 (x0,y0,x1,y1) 화면 비율, align은 center|left."""

    box: tuple[float, float, float, float]
    align: str
    max_ratio: float  # 최대 폰트 크기 = 화면 높이 * max_ratio


@dataclass(frozen=True)
class _Spec:
    # panels: (box, rgba|None) — color None이면 브랜드 강조색으로 채움
    panels: list[tuple[tuple[float, float, float, float], tuple[int, int, int, int] | None]]
    headline: _Block
    body: _Block
    cta: _Block


# 템플릿별 패널/텍스트 영역 — _TEXT_LAYOUT(영문 디자인 지시)을 좌표로 구현.
_TEMPLATE_SPECS: dict[TemplateType, _Spec] = {
    # A — 하단 다크 패널에 3요소 세로 정렬
    TemplateType.A: _Spec(
        panels=[((0.0, 0.55, 1.0, 1.0), (0, 0, 0, 190))],
        headline=_Block((0.06, 0.57, 0.94, 0.70), "center", 0.072),
        body=_Block((0.06, 0.705, 0.94, 0.82), "center", 0.040),
        cta=_Block((0.28, 0.835, 0.72, 0.95), "center", 0.044),
    ),
    # B — 상단 띠(헤드라인) + 하단 띠(본문·CTA)
    TemplateType.B: _Spec(
        panels=[
            ((0.0, 0.0, 1.0, 0.20), (0, 0, 0, 215)),
            ((0.0, 0.60, 1.0, 1.0), (0, 0, 0, 215)),
        ],
        headline=_Block((0.06, 0.02, 0.94, 0.18), "center", 0.066),
        body=_Block((0.06, 0.625, 0.94, 0.79), "center", 0.040),
        cta=_Block((0.28, 0.815, 0.72, 0.96), "center", 0.044),
    ),
    # C — 좌측 브랜드컬러 패널에 좌측정렬
    TemplateType.C: _Spec(
        panels=[((0.0, 0.0, 0.46, 1.0), None)],
        headline=_Block((0.04, 0.10, 0.42, 0.35), "left", 0.064),
        body=_Block((0.04, 0.37, 0.42, 0.60), "left", 0.038),
        cta=_Block((0.04, 0.70, 0.42, 0.85), "left", 0.044),
    ),
}


def _parse_color(value: str | None) -> tuple[int, int, int] | None:
    """#RRGGBB 형식의 브랜드 컬러를 RGB 튜플로 파싱. 실패 시 None."""
    if not value:
        return None
    hexstr = value.strip().lstrip("#")
    if len(hexstr) != 6:
        return None
    try:
        return tuple(int(hexstr[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return None


def _px(box: tuple[float, float, float, float], w: int, h: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))


def _wrap(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int
) -> list[str]:
    """공백 단위 우선 줄바꿈. 한 토큰이 너비를 넘으면 글자 단위로 분해(한글 대응)."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = word if not cur else f"{cur} {word}"
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
            cur = ""
        if draw.textlength(word, font=font) > max_w:
            chunk = ""
            for ch in word:
                if draw.textlength(chunk + ch, font=font) <= max_w:
                    chunk += ch
                else:
                    if chunk:
                        lines.append(chunk)
                    chunk = ch
            cur = chunk
        else:
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    box_w: int,
    box_h: int,
    max_size: int,
    min_size: int = 12,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """박스 안에 들어가는 가장 큰 폰트 크기를 찾아 (font, lines, line_height) 반환."""
    size = max(max_size, min_size)
    while size >= min_size:
        font = ImageFont.truetype(font_path, size)
        lines = _wrap(draw, text, font, box_w)
        ascent, descent = font.getmetrics()
        line_h = int((ascent + descent) * 1.25)
        widest = max((draw.textlength(ln, font=font) for ln in lines), default=0)
        if line_h * len(lines) <= box_h and widest <= box_w:
            return font, lines, line_h
        size -= 2
    font = ImageFont.truetype(font_path, min_size)
    lines = _wrap(draw, text, font, box_w)
    ascent, descent = font.getmetrics()
    return font, lines, int((ascent + descent) * 1.25)


def _draw_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    rect: tuple[int, int, int, int],
    font_path: str,
    max_size: int,
    color: tuple[int, int, int, int],
    align: str,
    stroke_fill: tuple[int, int, int, int] | None = None,
    shadow: bool = False,
) -> None:
    if not text:
        return
    x0, y0, x1, y1 = rect
    box_w, box_h = x1 - x0, y1 - y0
    font, lines, line_h = _fit(draw, text, font_path, box_w, box_h, max_size)
    # 패널 없는 floating/emotional은 외곽선+그림자로 사진 위 가독성을 확보.
    stroke_w = max(2, font.size // 14) if stroke_fill else 0
    shadow_off = max(1, font.size // 22)
    y = y0 + (box_h - line_h * len(lines)) // 2
    for line in lines:
        line_w = draw.textlength(line, font=font)
        x = x0 + (box_w - int(line_w)) // 2 if align == "center" else x0
        if shadow:
            draw.text((x + shadow_off, y + shadow_off), line, font=font, fill=(0, 0, 0, 90))
        draw.text(
            (x, y), line, font=font, fill=color, stroke_width=stroke_w, stroke_fill=stroke_fill
        )
        y += line_h


def _draw_cta(
    draw: ImageDraw.ImageDraw,
    text: str,
    rect: tuple[int, int, int, int],
    accent: tuple[int, int, int],
    align: str,
    template: TemplateType,
) -> None:
    if not text:
        return
    x0, y0, x1, y1 = rect
    box_w, box_h = x1 - x0, y1 - y0
    pad_x = int(box_h * 0.5)
    pad_y = int(box_h * 0.22)
    font, lines, _ = _fit(
        draw, text, _FONT_BOLD, box_w - 2 * pad_x, box_h - 2 * pad_y, int(box_h * 0.55)
    )
    line = lines[0] if lines else text
    text_w = int(draw.textlength(line, font=font))
    ascent, descent = font.getmetrics()
    text_h = ascent + descent
    btn_w = text_w + 2 * pad_x
    btn_h = text_h + 2 * pad_y
    bx = x0 + (box_w - btn_w) // 2 if align == "center" else x0
    by = y0 + (box_h - btn_h) // 2
    # C는 흰 버튼+브랜드 글자, A/B는 브랜드 버튼+흰 글자
    if template == TemplateType.C:
        fill, txt = _WHITE, (*accent, 255)
    else:
        fill, txt = (*accent, 255), _WHITE
    draw.rounded_rectangle([bx, by, bx + btn_w, by + btn_h], radius=btn_h // 2, fill=fill)
    draw.text((bx + pad_x, by + (btn_h - text_h) // 2), line, font=font, fill=txt)


def _draw_highlighted(
    draw: ImageDraw.ImageDraw,
    text: str,
    rect: tuple[int, int, int, int],
    font_path: str,
    max_size: int,
    base_color: tuple[int, int, int, int],
    accent: tuple[int, int, int],
    align: str,
) -> None:
    """헤드라인을 그리되 숫자가 포함된 단어만 강조색으로 칠한다(혜택 강조)."""
    if not text:
        return
    x0, y0, x1, y1 = rect
    box_w, box_h = x1 - x0, y1 - y0
    font, _, line_h = _fit(draw, text, font_path, box_w, box_h, max_size)
    space_w = draw.textlength(" ", font=font)
    # 단어 단위 줄바꿈(숫자 포함 단어 = 강조)
    lines: list[list[str]] = []
    cur: list[str] = []
    cur_w = 0.0
    for word in text.split():
        ww = draw.textlength(word, font=font)
        add = ww + (space_w if cur else 0)
        if cur and cur_w + add > box_w:
            lines.append(cur)
            cur, cur_w, add = [], 0.0, ww
        cur.append(word)
        cur_w += add
    if cur:
        lines.append(cur)

    accent_rgba = (*accent, 255)
    y = y0 + (box_h - line_h * len(lines)) // 2
    for line in lines:
        line_w = sum(draw.textlength(w, font=font) for w in line) + space_w * (len(line) - 1)
        x = x0 + (box_w - int(line_w)) // 2 if align == "center" else x0
        for word in line:
            fill = accent_rgba if _NUM_RE.search(word) else base_color
            draw.text((x, y), word, font=font, fill=fill)
            x += int(draw.textlength(word, font=font) + space_w)
        y += line_h


def _draw_star(draw: ImageDraw.ImageDraw, x: float, y: float, s: float, color=_GOLD) -> None:
    """좌상단 (x,y), 폭 s의 5각 별 하나를 채워 그린다."""
    cx, cy = x + s / 2, y + s / 2
    r_out, r_in = s / 2, s / 2 * 0.42
    pts = []
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        ang = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    draw.polygon(pts, fill=color)


def _draw_stars(
    draw: ImageDraw.ImageDraw, x: float, y: float, size: float, count: int = 5, color=_GOLD
) -> None:
    """별 count개를 가로로 나란히 그린다(별 한 개 폭 = size)."""
    gap = size * 0.28
    for i in range(count):
        _draw_star(draw, x + i * (size + gap), y, size, color)


def _draw_review_card(
    base: Image.Image,
    headline: str,
    body: str,
    cta: str,
    accent: tuple[int, int, int],
    w: int,
    h: int,
) -> Image.Image:
    """UGC 리뷰 카드 — 반투명 흰 카드에 별점·인용·리뷰어·CTA를 배치(사회적 증거)."""
    x0, y0 = int(0.06 * w), int(0.26 * h)
    x1, y1 = int(0.52 * w), int(0.80 * h)
    cw, ch = x1 - x0, y1 - y0
    pad = int(cw * 0.07)
    radius = int(min(cw, ch) * 0.05)

    # 카드 배경은 오버레이로 합성해 반투명 알파를 보장.
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle(
        [x0, y0, x1, y1], radius=radius, fill=(255, 255, 255, 235)
    )
    base = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(base)

    ix0, ix1 = x0 + pad, x1 - pad
    ih = ch - 2 * pad
    y = float(y0 + pad)

    def zone(frac: float) -> tuple[int, int]:
        nonlocal y
        top = int(y)
        y += ih * frac
        return top, int(y)

    t, b = zone(0.12)  # 별점
    _draw_stars(draw, ix0, t, (b - t) * 0.9)
    y += ih * 0.04
    t, b = zone(0.34)  # 인용(헤드라인)
    _draw_block(draw, headline, (ix0, t, ix1, b), _FONT_BOLD, int((b - t) * 0.42), _INK, "left")
    y += ih * 0.04
    t, b = zone(0.24)  # 본문
    _draw_block(draw, body, (ix0, t, ix1, b), _FONT_REGULAR, int((b - t) * 0.5), _GRAY, "left")
    y += ih * 0.04
    t, b = zone(0.16)  # CTA
    _draw_cta(draw, cta, (ix0, t, ix1, b), accent, "left", TemplateType.A)
    return base


def render_ad_text(
    image_bytes: bytes,
    headline: str,
    body: str,
    cta: str,
    template: TemplateType,
    brand_color: str | None = None,
    strategy: AdStrategy | None = None,
) -> bytes:
    """광고 카피를 템플릿 영역에 PIL로 렌더링한 PNG bytes를 반환한다.

    템플릿(A/B/C)이 텍스트 *위치*를, strategy의 StyleProfile이 *스타일*을 결정한다.
    - box: 반투명 패널 + 굵은 폰트(현행).
    - floating: 패널 없음 + 외곽선·그림자로 사진 위 가독성 확보.
    - emotional: 패널 없음 + 얇은 폰트 + 여백(폰트 축소) + 외곽선·그림자.
    """
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = base.size
    spec = _TEMPLATE_SPECS[template]

    profile = get_style(strategy) if strategy is not None else None
    style = profile.text_style if profile else "box"
    # accent_override(예: FOMO 코랄 레드)가 브랜드컬러보다 우선.
    accent_hex = (profile.accent_override if profile else None) or brand_color
    accent = _parse_color(accent_hex) or _DEFAULT_ACCENT
    if profile is not None:
        headline_color, body_color = profile.headline_color, profile.body_color
    else:
        headline_color, body_color = _WHITE, _LIGHT

    # review_card는 자체 카드 레이아웃을 그리고 바로 반환(템플릿 존 미사용).
    if style == "review_card":
        base = _draw_review_card(base, headline, body, cta, accent, w, h)
        out = io.BytesIO()
        base.save(out, format="PNG")
        return out.getvalue()

    # 스타일별 폰트·여백·외곽선/그림자.
    if style == "emotional":
        head_font, body_font, size_factor = _FONT_LIGHT, _FONT_LIGHT, 0.82
    else:
        head_font, body_font, size_factor = _FONT_BOLD, _FONT_REGULAR, 1.0
    floating = style in ("floating", "emotional")
    head_stroke = _contrast_stroke(headline_color) if floating else None
    body_stroke = _contrast_stroke(body_color) if floating else None

    # box 스타일만 반투명 패널을 합성. floating/emotional은 패널 없음.
    if style == "box":
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        for box, color in spec.panels:
            fill = color if color is not None else (*accent, 255)
            odraw.rectangle(_px(box, w, h), fill=fill)
        base = Image.alpha_composite(base, overlay)

    draw = ImageDraw.Draw(base)
    highlight = profile is not None and profile.highlight_numbers and bool(_NUM_RE.search(headline))
    if highlight:
        # 혜택 강조 box — 헤드라인 숫자만 강조색으로(예: "첫 구매 50% 할인").
        _draw_highlighted(
            draw,
            headline,
            _px(spec.headline.box, w, h),
            head_font,
            int(h * spec.headline.max_ratio * size_factor),
            headline_color,
            accent,
            spec.headline.align,
        )
    else:
        _draw_block(
            draw,
            headline,
            _px(spec.headline.box, w, h),
            head_font,
            int(h * spec.headline.max_ratio * size_factor),
            headline_color,
            spec.headline.align,
            stroke_fill=head_stroke,
            shadow=floating,
        )
    _draw_block(
        draw,
        body,
        _px(spec.body.box, w, h),
        body_font,
        int(h * spec.body.max_ratio * size_factor),
        body_color,
        spec.body.align,
        stroke_fill=body_stroke,
        shadow=floating,
    )
    _draw_cta(draw, cta, _px(spec.cta.box, w, h), accent, spec.cta.align, template)

    out = io.BytesIO()
    base.save(out, format="PNG")
    return out.getvalue()
