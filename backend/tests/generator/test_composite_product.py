# 상품 합성(composite_product) 단위 테스트 — 누끼 상품이 템플릿별 영역에 배치되는지 검증
import io

from PIL import Image

from domain.generator.contracts.enums import TemplateType
from domain.generator.pipeline.image_generator import composite_product


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _solid_bg(size: int = 200, color=(0, 0, 0, 255)) -> bytes:
    return _png_bytes(Image.new("RGBA", (size, size), color))


def _product(size: int = 80, color=(255, 0, 0, 255)) -> bytes:
    # 불투명 빨간 사각형(투명 배경 없는 단색) — 합성 위치 검증용
    return _png_bytes(Image.new("RGBA", (size, size), color))


def test_composite_returns_valid_png_same_size():
    out = composite_product(_solid_bg(), _product(), TemplateType.A)
    img = Image.open(io.BytesIO(out))
    assert img.size == (200, 200)
    assert img.format == "PNG"


def test_template_c_places_product_on_right():
    out = composite_product(_solid_bg(), _product(), TemplateType.C)
    img = Image.open(io.BytesIO(out)).convert("RGBA")
    w, h = img.size
    # 좌측 패널(텍스트 영역)에는 상품(빨강)이 없어야 함
    left_has_red = any(img.getpixel((x, h // 2))[0] > 200 for x in range(0, int(w * 0.40)))
    # 우측 영역에는 상품(빨강)이 있어야 함
    right_has_red = any(img.getpixel((x, h // 2))[0] > 200 for x in range(int(w * 0.55), w))
    assert not left_has_red
    assert right_has_red


def test_template_a_places_product_in_upper_half():
    out = composite_product(_solid_bg(), _product(), TemplateType.A)
    img = Image.open(io.BytesIO(out)).convert("RGBA")
    w, h = img.size
    # 상단 영역에 상품이 있어야 하고, 하단(텍스트 영역)에는 없어야 함
    upper_has_red = any(img.getpixel((w // 2, y))[0] > 200 for y in range(0, int(h * 0.52)))
    lower_has_red = any(img.getpixel((w // 2, y))[0] > 200 for y in range(int(h * 0.62), h))
    assert upper_has_red
    assert not lower_has_red
