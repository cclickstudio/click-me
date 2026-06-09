"""Ads router — 광고 업로드·분석·생성."""

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

router = APIRouter()


@router.post("/upload")
async def upload_ad(file: UploadFile = File(...)) -> dict:
    # TODO: S3 업로드 → Ad Understanding Agent 분석 트리거
    raise NotImplementedError


@router.get("/{ad_id}/analysis")
async def get_analysis(ad_id: str) -> dict:
    # TODO: 광고 구조화 분석 결과 반환
    raise NotImplementedError


@router.post("/{ad_id}/report")
async def generate_report(ad_id: str) -> dict:
    # TODO: PDF 리포트 생성 → S3 업로드 → presigned URL 반환
    raise NotImplementedError


class AdCompareRequest(BaseModel):
    ad_id_a: str
    ad_id_b: str


@router.post("/compare")
async def compare_ads(body: AdCompareRequest) -> dict:
    # TODO: A/B 비교 (7.8 목표)
    raise NotImplementedError
