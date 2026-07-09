# PIL 텍스트 렌더링(text_overlay) 단위 테스트 — 잘림 없이 그려지고 PNG 크기 보존 검증
import io

from PIL import Image

from domain.generator.contracts.enums import TemplateType
from domain.generator.pipeline.text_overlay import _fit, render_ad_text


def _solid(size: int = 512, color=(120, 120, 120, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (size, size), color).save(buf, format="PNG")
    return buf.getvalue()


def test_render_returns_same_size_png():
    out = render_ad_text(
        _solid(), "헤드라인 테스트", "본문 설명입니다", "지금 구매", TemplateType.A
    )
    img = Image.open(io.BytesIO(out))
    assert img.size == (512, 512)
    assert img.format == "PNG"


def test_render_all_templates():
    for t in (TemplateType.A, TemplateType.B, TemplateType.C):
        out = render_ad_text(_solid(), "헤드라인", "본문 텍스트", "클릭", t, brand_color="#ff8800")
        assert Image.open(io.BytesIO(out)).size == (512, 512)


def test_long_text_shrinks_to_fit_box():
    # 매우 긴 본문도 박스(폭) 안에 들어가도록 폰트가 줄어야 함
    img = Image.new("RGBA", (512, 512))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    long_text = "이것은 매우 긴 본문 텍스트입니다 " * 6
    box_w, box_h = 400, 120
    font, lines, line_h = _fit(draw, long_text, _font_regular(), box_w, box_h, max_size=40)
    # 모든 줄이 박스 폭 안 + 전체 높이가 박스 높이 안
    assert all(draw.textlength(ln, font=font) <= box_w for ln in lines)
    assert line_h * len(lines) <= box_h


def test_very_long_text_truncates_with_ellipsis():
    # 좁은 박스(템플릿 C 본문 폭 근사)에 최소 폰트로도 다 못 담을 만큼 긴 텍스트 —
    # 잘리지 않고 박스 밖으로 넘치면 안 되고, 들어가는 줄만 남기고 말줄임표(…)를 붙여야 함
    img = Image.new("RGBA", (512, 512))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    very_long_text = "광고 제작부터 관리까지 AI 하나로 해결하세요 업종별 맞춤 최적화로 더 빠르게 진행하세요 " * 5
    box_w, box_h = 195, 118  # 템플릿 C 본문 박스 근사치(512px 기준)
    font, lines, line_h = _fit(draw, very_long_text, _font_regular(), box_w, box_h, max_size=40)
    assert line_h * len(lines) <= box_h
    assert lines[-1].endswith("…")


def _font_regular() -> str:
    from domain.generator.pipeline.text_overlay import _resolve_font

    return _resolve_font("regular")
