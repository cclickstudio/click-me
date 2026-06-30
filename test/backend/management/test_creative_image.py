# 이미지 규격 검증·변환 유틸 테스트
import io

import pytest
from PIL import Image

from domain.management.adapters.meta.creative_image import (
    ImageSpecError,
    to_meta_jpeg,
    validate_image_spec,
)


def _png(w: int, h: int, mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, (w, h), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_validate_rejects_too_small():
    with pytest.raises(ImageSpecError, match="최소"):
        validate_image_spec(_png(100, 100))


def test_validate_rejects_extreme_ratio():
    # 두 변 모두 최소(600) 이상이되 비율만 범위 밖(2.16:1) — 비율 분기를 격리해 검증.
    with pytest.raises(ImageSpecError, match="비율"):
        validate_image_spec(_png(1300, 600))


def test_validate_rejects_oversized_dimensions():
    # 픽셀/차원 상한(리뷰 P3-2) — 압축폭탄 방지. _MAX_SIDE 초과는 거부.
    with pytest.raises(ImageSpecError, match="너무 큼"):
        validate_image_spec(_png(7000, 1080))


def test_to_meta_jpeg_converts_rgba_to_rgb_jpeg():
    out = to_meta_jpeg(_png(1080, 1080, mode="RGBA"))
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.mode == "RGB"
