# 광고 카피(헤드라인·본문·CTA)를 PIL로 직접 렌더링 — 확산모델 텍스트 잘림·오탈자 방지
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

from domain.generator.contracts.enums import AdStrategy, TemplateType
from domain.generator.pipeline.style_profile import get_style

_FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"
_FONT_BOLD = str(_FONT_DIR / "Pretendard-Bold.otf")
_FONT_REGULAR = str(_FONT_DIR / "Pretendard-Regular.otf")

# KB Typography System의 전략별 웨이트 → 실제 Pretendard 파일.
# 웨이트별 굵기값(100~900)으로 보유 파일 중 가장 가까운 것을 고른다 → 누락 웨이트는
# 자동 폴백되고, 해당 .otf를 fonts/에 넣으면 그 웨이트가 즉시 적용된다(현재는 Bold·Regular만 보유).
_WEIGHT_VALUE: dict[str, int] = {
    "thin": 100,
    "extralight": 200,
    "light": 300,
    "regular": 400,
    "medium": 500,
    "semibold": 600,
    "bold": 700,
    "extrabold": 800,
    "black": 900,
}
_WEIGHT_FILENAME: dict[str, str] = {
    "thin": "Pretendard-Thin.otf",
    "extralight": "Pretendard-ExtraLight.otf",
    "light": "Pretendard-Light.otf",
    "regular": "Pretendard-Regular.otf",
    "medium": "Pretendard-Medium.otf",
    "semibold": "Pretendard-SemiBold.otf",
    "bold": "Pretendard-Bold.otf",
    "extrabold": "Pretendard-ExtraBold.otf",
    "black": "Pretendard-Black.otf",
}


@cache
def _resolve_font(weight: str) -> str:
    """전략이 지정한 폰트 웨이트를 실제 파일 경로로 해석한다.

    해당 웨이트 .otf가 없으면 보유한 웨이트 중 굵기값이 가장 가까운 파일로 폴백한다
    (동률이면 더 굵은 쪽). 보유 파일이 전혀 없으면 Regular. 누락 웨이트 .otf를
    assets/fonts/에 추가하면 캐시만 비우면 자동 반영된다.
    """
    target = _WEIGHT_VALUE.get(weight, 700)
    available = [
        (_WEIGHT_VALUE[name], _FONT_DIR / fname)
        for name, fname in _WEIGHT_FILENAME.items()
        if (_FONT_DIR / fname).exists()
    ]
    if not available:
        return _FONT_REGULAR
    _, path = min(available, key=lambda vp: (abs(vp[0] - target), -vp[0]))
    return str(path)


_DEFAULT_ACCENT = (37, 99, 235)  # brand_color 없을 때 기본 강조색(파랑)
_WHITE = (255, 255, 255, 255)
_LIGHT = (235, 235, 235, 255)
_DARK_TEXT = (51, 51, 51, 255)  # 밝은 배경 위에 쓸 어두운 텍스트색(순검정 대신 부드러운 톤)
_BRIGHTNESS_THRESHOLD = 140.0

# 숫자 토큰(할인율·수량·기간 등) — 단어에 숫자가 포함되면 강조 대상으로 본다.
_NUM_RE = re.compile(r"\d")


def _sample_brightness(base: Image.Image, rect: tuple[int, int, int, int]) -> float:
    """rect 영역(텍스트가 그려질 자리)의 평균 밝기(0~255)를 구한다.

    패널 없는 floating/emotional 스타일은 사진이 그대로 비치므로, 전략별 고정 텍스트색
    대신 실제로 그 자리에 뭐가 있는지 보고 텍스트색을 정하는 게 더 안전하다.
    """
    x0, y0, x1, y1 = rect
    if x1 <= x0 or y1 <= y0:
        return 128.0
    region = base.convert("RGB").crop((x0, y0, x1, y1))
    return ImageStat.Stat(region.convert("L")).mean[0]


def _adaptive_text_color(brightness: float) -> tuple[int, int, int, int]:
    """배경이 어두우면 흰색, 밝으면 어두운 톤 텍스트색을 고른다."""
    return _WHITE if brightness < _BRIGHTNESS_THRESHOLD else _DARK_TEXT


def _shadow_color_for(text_color: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """선택된 텍스트색과 반대 밝기의 반투명 그림자색 — 국지적으로 밝기가 섞인 배경에서도
    텍스트색 하나만으로 커버 안 되는 부분을 부드러운 그림자로 보강한다."""
    r, g, b = text_color[:3]
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return (0, 0, 0, 110) if luminance >= _BRIGHTNESS_THRESHOLD else (255, 255, 255, 140)


def _accent_or_tint(
    accent: tuple[int, int, int], threshold: float = 140.0
) -> tuple[int, int, int, int]:
    """강조색이 threshold보다 어두우면 흰색과 섞어(tint) 색조는 유지한 채 최소 밝기를 확보한다.

    box 스타일 패널이 항상 짙은 반투명 검정(예: 템플릿 A의 (0,0,0,190))이라,
    실제 배경 픽셀 샘플링 없이 강조색 자체의 밝기만 봐도 대비 확보가 충분하다.
    """
    r, g, b = accent
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    if luminance >= threshold:
        return (*accent, 255)
    t = (threshold - luminance) / (255 - luminance)
    tinted = tuple(int(c + (255 - c) * t) for c in (r, g, b))
    return (*tinted, 255)


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
    base: Image.Image,
    text: str,
    rect: tuple[int, int, int, int],
    font_path: str,
    max_size: int,
    color: tuple[int, int, int, int],
    align: str,
    soft_shadow_color: tuple[int, int, int, int] | None = None,
) -> Image.Image:
    """텍스트를 rect 안에 그린다. soft_shadow_color가 있으면 딱딱한 외곽선 대신
    부드럽게 블러 처리된 그림자를 텍스트 뒤에 먼저 합성한 뒤 텍스트를 그린다
    (패널 없는 floating/emotional 스타일의 사진 위 가독성 보강용)."""
    if not text:
        return base
    draw = ImageDraw.Draw(base)
    x0, y0, x1, y1 = rect
    box_w, box_h = x1 - x0, y1 - y0
    font, lines, line_h = _fit(draw, text, font_path, box_w, box_h, max_size)
    y = y0 + (box_h - line_h * len(lines)) // 2

    if soft_shadow_color is not None:
        shadow_off = max(1, font.size // 18)
        shadow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow_layer)
        sy = y
        for line in lines:
            line_w = sdraw.textlength(line, font=font)
            sx = x0 + (box_w - int(line_w)) // 2 if align == "center" else x0
            sdraw.text((sx + shadow_off, sy + shadow_off), line, font=font, fill=soft_shadow_color)
            sy += line_h
        blur_radius = max(2, font.size // 12)
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur_radius))
        base = Image.alpha_composite(base, shadow_layer)
        draw = ImageDraw.Draw(base)

    for line in lines:
        line_w = draw.textlength(line, font=font)
        x = x0 + (box_w - int(line_w)) // 2 if align == "center" else x0
        draw.text((x, y), line, font=font, fill=color)
        y += line_h
    return base


def _draw_cta(
    base: Image.Image,
    text: str,
    rect: tuple[int, int, int, int],
    accent: tuple[int, int, int],
    align: str,
    template: TemplateType,
    font_path: str = _FONT_BOLD,
    floating: bool = False,
) -> Image.Image:
    draw = ImageDraw.Draw(base)
    if not text:
        return base
    x0, y0, x1, y1 = rect
    box_w, box_h = x1 - x0, y1 - y0
    # 여백을 높이에만 비례시키면 템플릿 C처럼 폭이 좁은 박스에서 여백이 폭 대부분을 먹어
    # 버튼이 박스에 비해 부자연스럽게 좁아진다 — 폭 기준 상한을 같이 둬서 방지한다.
    pad_x = int(min(box_h * 0.5, box_w * 0.18))
    pad_y = int(box_h * 0.22)
    font, lines, _ = _fit(
        draw, text, font_path, box_w - 2 * pad_x, box_h - 2 * pad_y, int(box_h * 0.55)
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
    # floating/emotional은 패널 없이 사진 위에 바로 얹혀서, 사진의 밝은 영역과 버튼이 섞여
    # 보일 수 있다 — 텍스트에 붙이는 것과 같은 그림자를 버튼에도 붙여 경계를 항상 드러낸다.
    # 별도 레이어에 그린 뒤 블러 처리해 합성 — 딱딱한 사각형이 아닌 부드러운 그림자가 되게 한다.
    if floating:
        shadow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        shadow_off = max(2, btn_h // 20)
        ImageDraw.Draw(shadow_layer).rounded_rectangle(
            [bx + shadow_off, by + shadow_off, bx + btn_w + shadow_off, by + btn_h + shadow_off],
            radius=btn_h // 2,
            fill=(0, 0, 0, 110),
        )
        blur_radius = max(2, btn_h // 10)
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur_radius))
        base = Image.alpha_composite(base, shadow_layer)
        draw = ImageDraw.Draw(base)
    draw.rounded_rectangle([bx, by, bx + btn_w, by + btn_h], radius=btn_h // 2, fill=fill)
    draw.text((bx + pad_x, by + (btn_h - text_h) // 2), line, font=font, fill=txt)
    return base


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

    accent_rgba = _accent_or_tint(accent)
    y = y0 + (box_h - line_h * len(lines)) // 2
    for line in lines:
        line_w = sum(draw.textlength(w, font=font) for w in line) + space_w * (len(line) - 1)
        x = x0 + (box_w - int(line_w)) // 2 if align == "center" else x0
        for word in line:
            fill = accent_rgba if _NUM_RE.search(word) else base_color
            draw.text((x, y), word, font=font, fill=fill)
            x += int(draw.textlength(word, font=font) + space_w)
        y += line_h


def render_ad_text(
    image_bytes: bytes,
    headline: str,
    body: str,
    cta: str,
    template: TemplateType | None,
    brand_color: str | None = None,
    strategy: AdStrategy | None = None,
) -> bytes:
    """광고 카피를 템플릿 영역에 PIL로 렌더링한 PNG bytes를 반환한다.

    템플릿(A/B/C)이 텍스트 *위치*를, strategy의 StyleProfile이 *스타일*을 결정한다.
    template=None(개선 모드 자유 레이아웃)이면 Template A 레이아웃으로 폴백.
    - box: 반투명 패널 + 굵은 폰트(현행).
    - floating/emotional: 패널 없음 — 텍스트색은 그 자리 배경 밝기를 직접 재서 적응적으로
      정하고(_adaptive_text_color), 부드러운 블러 그림자로 국지적 대비를 보강한다
      (딱딱한 외곽선은 "스티커처럼 보인다"는 피드백으로 제거함). emotional은 폰트도 축소.
    """
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = base.size
    spec = _TEMPLATE_SPECS[template if template is not None else TemplateType.A]

    profile = get_style(strategy) if strategy is not None else None
    style = profile.text_style if profile else "box"
    # accent_override(예: FOMO 코랄 레드)가 브랜드컬러보다 우선.
    accent_hex = (profile.accent_override if profile else None) or brand_color
    accent = _parse_color(accent_hex) or _DEFAULT_ACCENT

    # 전략별 폰트 웨이트(KB Typography) → 실제 폰트 파일. 프로필 없으면 Bold/Regular 기본.
    if profile is not None:
        head_font = _resolve_font(profile.headline_weight)
        body_font = _resolve_font(profile.body_weight)
        cta_font = _resolve_font(profile.cta_weight)
    else:
        head_font, body_font, cta_font = _FONT_BOLD, _FONT_REGULAR, _FONT_BOLD

    # 감성형은 여백을 위해 폰트를 축소. 그 외는 원래 크기.
    size_factor = 0.82 if style == "emotional" else 1.0
    floating = style in ("floating", "emotional")

    if floating:
        # 패널이 없어 사진이 그대로 비치므로, 전략별 고정색(profile.headline/body_color) 대신
        # 실제 그 자리의 밝기를 재서 흰색/어두운 톤 중 더 잘 보이는 쪽을 고른다.
        headline_color = _adaptive_text_color(
            _sample_brightness(base, _px(spec.headline.box, w, h))
        )
        body_color = _adaptive_text_color(_sample_brightness(base, _px(spec.body.box, w, h)))
        head_shadow: tuple[int, int, int, int] | None = _shadow_color_for(headline_color)
        body_shadow: tuple[int, int, int, int] | None = _shadow_color_for(body_color)
    elif profile is not None:
        headline_color, body_color = profile.headline_color, profile.body_color
        head_shadow = body_shadow = None
    else:
        headline_color, body_color = _WHITE, _LIGHT
        head_shadow = body_shadow = None

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
        base = _draw_block(
            base,
            headline,
            _px(spec.headline.box, w, h),
            head_font,
            int(h * spec.headline.max_ratio * size_factor),
            headline_color,
            spec.headline.align,
            soft_shadow_color=head_shadow,
        )
    base = _draw_block(
        base,
        body,
        _px(spec.body.box, w, h),
        body_font,
        int(h * spec.body.max_ratio * size_factor),
        body_color,
        spec.body.align,
        soft_shadow_color=body_shadow,
    )
    base = _draw_cta(
        base,
        cta,
        _px(spec.cta.box, w, h),
        accent,
        spec.cta.align,
        template if template is not None else TemplateType.A,
        cta_font,
        floating=floating,
    )

    out = io.BytesIO()
    base.save(out, format="PNG")
    return out.getvalue()
