"""S3 스토리지 툴 — 광고 파일 업로드 / Presigned URL 생성."""

import uuid

import aioboto3
from langchain_core.tools import tool

from core.config import settings

session = aioboto3.Session()


@tool
async def upload_file(file_bytes: bytes, content_type: str, prefix: str = "ads") -> str:
    """파일을 S3에 업로드하고 S3 key를 반환합니다."""
    key = f"{prefix}/{uuid.uuid4()}"
    async with session.client("s3", region_name=settings.aws_region) as s3:
        await s3.put_object(
            Bucket=settings.s3_bucket_name,
            Key=key,
            Body=file_bytes,
            ContentType=content_type,
        )
    return key


@tool
async def get_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    """S3 객체의 Presigned URL을 생성합니다."""
    async with session.client("s3", region_name=settings.aws_region) as s3:
        return await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket_name, "Key": s3_key},
            ExpiresIn=expires_in,
        )
