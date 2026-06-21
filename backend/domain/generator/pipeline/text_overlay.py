# 광고 카피(헤드라인·본문·CTA)를 PIL로 직접 렌더링 — 확산모델 텍스트 잘림·오탈자 방지
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from domain.generator.contracts.enums import TemplateType

_FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"
_FONT_BOLD = str(_FONT_DIR / "Pretendard-Bold.otf")
_FONT_REGULAR = str(_FONT_DIR / "Pretendard-Regular.otf")

_DEFAULT_ACCENT = (37, 99, 235)  # brand_color 없을 때 기본 강조색(파랑)
_WHITE = (255, 255, 255, 255)
_LIGHT = (235, 235, 235, 255)


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
) -> None:
    if not text:
        return
    x0, y0, x1, y1 = rect
    box_w, box_h = x1 - x0, y1 - y0
    font, lines, line_h = _fit(draw, text, font_path, box_w, box_h, max_size)
    y = y0 + (box_h - line_h * len(lines)) // 2
    for line in lines:
        line_w = draw.textlength(line, font=font)
        x = x0 + (box_w - int(line_w)) // 2 if align == "center" else x0
        draw.text((x, y), line, font=font, fill=color)
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


def render_ad_text(
    image_bytes: bytes,
    headline: str,
    body: str,
    cta: str,
    template: TemplateType,
    brand_color: str | None = None,
) -> bytes:
    """광고 카피를 템플릿 영역에 PIL로 렌더링한 PNG bytes를 반환한다."""
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = base.size
    spec = _TEMPLATE_SPECS[template]
    accent = _parse_color(brand_color) or _DEFAULT_ACCENT

    # 패널을 반투명 오버레이로 합성
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for box, color in spec.panels:
        fill = color if color is not None else (*accent, 255)
        odraw.rectangle(_px(box, w, h), fill=fill)
    base = Image.alpha_composite(base, overlay)

    draw = ImageDraw.Draw(base)
    _draw_block(
        draw,
        headline,
        _px(spec.headline.box, w, h),
        _FONT_BOLD,
        int(h * spec.headline.max_ratio),
        _WHITE,
        spec.headline.align,
    )
    _draw_block(
        draw,
        body,
        _px(spec.body.box, w, h),
        _FONT_REGULAR,
        int(h * spec.body.max_ratio),
        _LIGHT,
        spec.body.align,
    )
    _draw_cta(draw, cta, _px(spec.cta.box, w, h), accent, spec.cta.align, template)

    out = io.BytesIO()
    base.save(out, format="PNG")
    return out.getvalue()
