import uuid

import aioboto3
from fastapi import APIRouter, HTTPException, UploadFile

from core.config import settings
from domain.generator.contracts.schemas import GenerateRequest, GenerateResult, ImproveRequest
from domain.generator.service.generator_service import generate_ad, improve_ad

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/generate", response_model=GenerateResult)
async def generate(body: GenerateRequest) -> GenerateResult:
    return await generate_ad(body)


@router.post("/improve", response_model=GenerateResult)
async def improve(body: ImproveRequest) -> GenerateResult:
    return await improve_ad(body)


@router.post("/upload")
async def upload_ad_image(file: UploadFile) -> dict:
    """로컬 이미지 파일을 S3에 업로드하고 S3 키를 반환한다.
    개선 모드에서 파일을 직접 업로드할 때 사용한다.
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "지원하지 않는 파일 형식입니다. PNG, JPEG, WebP만 허용됩니다. "
                f"(받은 형식: {file.content_type})"
            ),
        )

    image_bytes = await file.read()

    if len(image_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="파일 크기가 10MB를 초과합니다.",
        )

    ext = (
        file.filename.rsplit(".", 1)[-1].lower()
        if file.filename and "." in file.filename
        else "png"
    )
    s3_key = f"uploads/{uuid.uuid4()}/original.{ext}"

    session = aioboto3.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    async with session.client("s3") as s3:
        await s3.put_object(
            Bucket=settings.s3_bucket_name,
            Key=s3_key,
            Body=image_bytes,
            ContentType=file.content_type,
        )

    return {"s3_key": s3_key, "filename": file.filename}
