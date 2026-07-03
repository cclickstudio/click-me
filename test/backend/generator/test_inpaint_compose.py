# 인페인팅 베이스/마스크 생성 단위 테스트 — 상품이 템플릿 영역에 잠기는지 검증
import io

from PIL import Image

from domain.generator.contracts.enums import AdSize, TemplateType
from domain.generator.pipeline.image_generator import _build_inpaint_base_and_mask


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _product(size: int = 80, color=(255, 0, 0, 255)) -> bytes:
    # 불투명 빨간 사각형 — 배치/마스크 위치 검증용
    return _png_bytes(Image.new("RGBA", (size, size), color))


def test_base_and_mask_match_ad_size():
    base_png, mask_png = _build_inpaint_base_and_mask(
        _product(), TemplateType.A, AdSize.SQUARE, 0.5
    )
    base = Image.open(io.BytesIO(base_png))
    mask = Image.open(io.BytesIO(mask_png))
    assert base.size == (1024, 1024)
    assert mask.size == (1024, 1024)


def test_mask_opaque_only_on_product_region():
    # 마스크는 상품 실루엣에서만 불투명(보존), 나머지는 투명(생성 대상)이어야 함
    _, mask_png = _build_inpaint_base_and_mask(_product(), TemplateType.A, AdSize.SQUARE, 0.5)
    mask = Image.open(io.BytesIO(mask_png)).convert("RGBA")
    alpha = mask.split()[3]
    # 상품은 상단 영역에 배치 → 상단 중앙은 불투명, 하단(텍스트 영역)은 투명
    w, h = mask.size
    assert alpha.getpixel((w // 2, int(h * 0.25))) == 255  # 상품 영역 → 보존
    assert alpha.getpixel((w // 2, int(h * 0.90))) == 0  # 하단 → 생성 대상


def test_template_c_locks_product_on_right():
    _, mask_png = _build_inpaint_base_and_mask(_product(), TemplateType.C, AdSize.SQUARE, 0.5)
    alpha = Image.open(io.BytesIO(mask_png)).convert("RGBA").split()[3]
    w, h = alpha.size
    # 좌측 패널(텍스트 영역)은 투명, 우측(상품)은 불투명
    left_opaque = any(alpha.getpixel((x, h // 2)) == 255 for x in range(0, int(w * 0.40)))
    right_opaque = any(alpha.getpixel((x, h // 2)) == 255 for x in range(int(w * 0.55), w))
    assert not left_opaque
    assert right_opaque
