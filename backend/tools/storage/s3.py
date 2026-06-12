"""S3 스토리지 유틸 — 생성 광고 이미지 업로드 및 presigned URL 발급."""

from __future__ import annotations

import aioboto3

from core.config import settings

_session = aioboto3.Session(
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)


def candidate_key(generation_id: str, idx: int) -> str:
    """생성 후보 이미지(PNG)의 S3 키."""
    return f"generated-ads/{generation_id}/candidate-{idx}.png"


def publish_key(generation_id: str, idx: int) -> str:
    """Instagram 게시용 JPEG 변환본의 S3 키."""
    return f"generated-ads/{generation_id}/candidate-{idx}-publish.jpg"


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


async def presign_get(key: str, expires_in: int = 3600) -> str:
    """다운로드용 presigned URL을 발급한다 (기본 1시간)."""
    async with _session.client("s3") as s3:
        return await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket_name, "Key": key},
            ExpiresIn=expires_in,
        )
