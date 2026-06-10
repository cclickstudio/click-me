import uuid

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from core.schemas import AdAnalysisResult
from tools.ad_analysis.vision import run_ad_understanding

router = APIRouter()


@router.post("/analyze/image", response_model=AdAnalysisResult)
async def analyze_image(body: dict):
    ad_id = body.get("ad_id", str(uuid.uuid4()))
    image_url = body.get("image_url", "")
    return await run_ad_understanding(
        ad_id=ad_id, ad_type="image", ad_content=f"[이미지] {image_url}"
    )


@router.post("/analyze/text", response_model=AdAnalysisResult)
async def analyze_text(body: dict):
    ad_id = body.get("ad_id", str(uuid.uuid4()))
    text_content = body.get("text_content", {})
    ad_content = f"헤드라인: {text_content.get('headline', '')}\n본문: {text_content.get('body', '')}\nCTA: {text_content.get('cta', '')}"
    return await run_ad_understanding(ad_id=ad_id, ad_type="text", ad_content=ad_content)


@router.post("/upload")
async def upload_ad(file: UploadFile = File(...), project_id: str = Form(...)):
    ad_id = str(uuid.uuid4())
    # TODO: S3 upload
    return {
        "ad_id": ad_id,
        "s3_url": f"https://placeholder.s3.amazonaws.com/{ad_id}",
        "presigned_url": f"https://placeholder.s3.amazonaws.com/{ad_id}?presigned=1",
    }


class AdCompareRequest(BaseModel):
    ad_id_a: str
    ad_id_b: str


@router.post("/compare")
async def compare_ads(body: AdCompareRequest) -> dict:
    # A/B 비교 — 7.8 목표
    raise NotImplementedError
