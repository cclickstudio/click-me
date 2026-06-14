"""텍스트 합성(Pillow) 테스트 — 배경 위에 카피를 렌더해 유효 PNG를 만든다 (네트워크 없음)."""

import io

from PIL import Image

from domain.generator.contracts.schemas import AdCopy
from domain.generator.contracts.templates import get_template
from domain.generator.render.text_overlay import _hex_to_rgb, compose_ad_image


def _solid_png(size: int = 512, color=(200, 200, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buf, format="PNG")
    return buf.getvalue()


COPY = AdCopy(
    headline="여름 준비 끝, 시원한 하루",
    subcopy="조용한 바람으로 채우는 밤",
    benefit_text="오늘만 30% 할인 + 무료배송",
    cta="지금 구매하기",
)


def test_pixel_box_maps_percent_to_pixels():
    area = get_template("A").area_by_role("cta")
    x0, y0, x1, y1 = area.pixel_box(1000, 1000)
    assert (x0, y0, x1, y1) == (200, 850, 800, 920)


def test_compose_returns_valid_png_same_size():
    bg = _solid_png(640)
    out = compose_ad_image(bg, COPY, get_template("A"), brand_color="#FF5733")
    img = Image.open(io.BytesIO(out))
    assert img.format == "PNG"
    assert img.size == (640, 640)


def test_compose_changes_pixels():
    """합성 후 픽셀이 배경 단색과 달라야 한다 (텍스트가 그려졌는지)."""
    bg = _solid_png(640, color=(200, 200, 200))
    out = compose_ad_image(bg, COPY, get_template("B"), brand_color="#3182F6")
    assert out != bg
    colors = Image.open(io.BytesIO(out)).convert("RGB").getcolors(maxcolors=100000)
    assert colors is not None and len(colors) > 1  # 단색이 아님


def test_compose_handles_empty_subcopy():
    out = compose_ad_image(
        _solid_png(512),
        AdCopy(headline="헤드라인", subcopy="", benefit_text="혜택", cta="구매"),
        get_template("C"),
    )
    assert Image.open(io.BytesIO(out)).size == (512, 512)


def test_hex_to_rgb_parsing():
    assert _hex_to_rgb("#FF5733") == (255, 87, 51)
    assert _hex_to_rgb("3182F6") == (49, 130, 246)
    assert _hex_to_rgb(None) == (49, 130, 246)  # 기본 브랜드 컬러
    assert _hex_to_rgb("zzzzzz") == (49, 130, 246)  # 16진수 아님 → 폴백
