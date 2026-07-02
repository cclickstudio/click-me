# Meta 광고 소재 업로드 전 규격 검증 + PNG→JPEG 변환 유틸
from __future__ import annotations

import io

from PIL import Image

# Meta 권장 기준(보수적 v1) — 정사각/세로 피드 최소.
_MIN_SIDE = 600
_MAX_SIDE = 6000  # 한 변 상한(초대형 거부)
_MAX_PIXELS = 30_000_000  # 총 픽셀 상한 — 압축폭탄 방지(리뷰 P3-2)
_MIN_RATIO, _MAX_RATIO = 0.5, 1.91  # 세로 1:2 ~ 가로 1.91:1
_MAX_BYTES = 30 * 1024 * 1024  # 30MB
_JPEG_QUALITY = 90

# (PIL 전역 Image.MAX_IMAGE_PIXELS는 건드리지 않는다 — 다른 모듈/테스트 사이드이펙트, 리뷰 P2.
#  대신 validate_image_spec이 헤더에서 직접 width/height/pixel을 검사한다.)


class ImageSpecError(ValueError):
    """이미지가 Meta 업로드 규격에 맞지 않음 — 라우터가 422로 변환."""


def validate_image_spec(image_bytes: bytes) -> None:
    if len(image_bytes) > _MAX_BYTES:
        raise ImageSpecError(f"파일 크기 초과(최대 {_MAX_BYTES // (1024 * 1024)}MB)")
    try:
        # 헤더만으로 크기 확인(전체 디코드 전) — 차원/픽셀 상한 위반은 디코드 없이 거부.
        with Image.open(io.BytesIO(image_bytes)) as probe:
            w, h = probe.size
        if w > _MAX_SIDE or h > _MAX_SIDE or (w * h) > _MAX_PIXELS:
            raise ImageSpecError(
                f"이미지가 너무 큼(최대 {_MAX_SIDE}px·{_MAX_PIXELS}px², 현재 {w}x{h})"
            )
        with Image.open(io.BytesIO(image_bytes)) as verifier:
            verifier.verify()  # 손상 검사
    except ImageSpecError:
        raise
    except Exception as exc:  # noqa: BLE001 — 손상/비이미지/폭탄
        raise ImageSpecError("이미지를 열 수 없음(손상/비이미지/초대형)") from exc
    if min(w, h) < _MIN_SIDE:
        raise ImageSpecError(f"최소 한 변 {_MIN_SIDE}px 필요(현재 {w}x{h})")
    ratio = w / h if h else 0
    if not (_MIN_RATIO <= ratio <= _MAX_RATIO):
        raise ImageSpecError(f"가로세로 비율 범위 밖({_MIN_RATIO}~{_MAX_RATIO}, 현재 {ratio:.2f})")


def to_meta_jpeg(image_bytes: bytes) -> bytes:
    """RGBA/팔레트/투명 alpha를 흰 배경 RGB로 합성 후 JPEG 인코딩(Meta는 JPEG 권장).

    public util이므로 디코드 前 스스로 규격을 재검증한다(다른 호출자가 우회 못 하게, 리뷰 P2).
    엔드포인트 흐름에선 validate가 한 번 더 도는 셈이지만 헤더 검사라 저렴하다.
    """
    validate_image_spec(image_bytes)
    out = io.BytesIO()
    with Image.open(io.BytesIO(image_bytes)) as src:  # 핸들 누수 방지(코드리뷰 Q4)
        if src.mode in ("RGBA", "LA", "P"):
            rgba = src.convert("RGBA")
            img = Image.new("RGB", rgba.size, "white")
            img.paste(rgba, mask=rgba.split()[-1])
        else:
            img = src.convert("RGB")
        img.save(out, format="JPEG", quality=_JPEG_QUALITY)
    return out.getvalue()
