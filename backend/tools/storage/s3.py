"""S3 스토리지 유틸 — 생성 광고 이미지 업로드 및 presigned URL 발급."""

from __future__ import annotations

import uuid

import aioboto3

from core.config import settings

_session = aioboto3.Session(
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)


def brand_logo_key(client_id: str, ext: str) -> str:
    """브랜드 로고의 S3 키 — 업로드마다 고유(키트별 개별 로고 보존)."""
    return f"brand-logos/{client_id}/{uuid.uuid4().hex}.{ext.lstrip('.')}"


def candidate_key(generation_id: str, idx: int) -> str:
    """생성 후보 이미지(PNG)의 S3 키 — 텍스트·로고까지 합성된 최종본."""
    return f"generated-ads/{generation_id}/candidate-{idx}.png"


def candidate_base_key(generation_id: str, idx: int) -> str:
    """후보의 텍스트 없는 base 이미지 S3 키 — 플랫폼별 리레이아웃 렌더의 원본."""
    return f"generated-ads/{generation_id}/candidate-{idx}-base.png"


def publish_key(generation_id: str, idx: int) -> str:
    """Instagram 게시용 JPEG 변환본의 S3 키."""
    return f"generated-ads/{generation_id}/candidate-{idx}-publish.jpg"


def temp_product_image_key(temp_id: str) -> str:
    """상품 이미지 임시 저장 S3 키 — 서버 재시작 후에도 유지, 생성 파이프라인 내부 전달용."""
    return f"temp-product-images/{temp_id}.png"


def product_cutout_key(generation_id: str) -> str:
    """누끼(배경 제거) 상품 이미지 S3 키 — 생성 모드에서 저장, 개선 모드에서 재사용."""
    return f"temp-product-images/{generation_id}-cutout.png"


async def upload_bytes(data: bytes, key: str, content_type: str = "image/png") -> str:
    """바이트를 S3에 업로드하고 키를 반환한다."""
    async with _session.client("s3") as s3:
        await s3.put_object(
            Bucket=settings.s3_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    return key


async def download_bytes(key: str) -> bytes:
    """S3 객체를 바이트로 다운로드한다."""
    async with _session.client("s3") as s3:
        obj = await s3.get_object(Bucket=settings.s3_bucket_name, Key=key)
        return await obj["Body"].read()


async def presign_get(key: str, expires_in: int = 3600) -> str | None:
    """다운로드용 presigned URL을 발급한다 (기본 1시간). 실패 시 None 반환."""
    import logging

    try:
        async with _session.client("s3") as s3:
            url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.s3_bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            logging.getLogger("clickme").debug("presign_get OK: key=%s", key)
            return url
    except Exception as exc:
        logging.getLogger("clickme").warning("presign_get 실패: key=%s, error=%s", key, exc)
        return None
