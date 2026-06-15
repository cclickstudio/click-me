"""광고 제너레이터 API — graph 파이프라인 기반.

생성 시작(생성/개선) / SSE 스트림 / 결과 조회 / 후보 선택 / 게시 / 광고집행 / 이력.
"""

import io
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image
from pydantic import BaseModel

from core.auth import get_current_user
from core.models import User
from domain.generator.adapters.meta_ads import AdvertiseRequest
from domain.generator.contracts.schemas import GenerationCreateRequest
from domain.generator.service import generator_service
from domain.generator.service.brand_profile import get_profile, save_profile
from tools.storage.s3 import brand_logo_key, presign_get, upload_bytes

router = APIRouter()

_ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}


class BrandProfileBody(BaseModel):
    brand_color: str | None = None
    brand_logo_key: str | None = None
    tone_and_manner: str | None = None


@router.get("/brand-profile")
async def get_brand_profile(x_client_id: str = Header()):
    """저장된 브랜드 프로필 조회 — 로고 S3 키가 있으면 presigned URL도 반환."""
    p = get_profile(x_client_id)
    logo_url: str | None = None
    if p.brand_logo_key:
        try:
            logo_url = await presign_get(p.brand_logo_key)
        except Exception:
            logo_url = None
    return {
        "brand_color": p.brand_color,
        "brand_logo_key": p.brand_logo_key,
        "brand_logo_url": logo_url,
        "tone_and_manner": p.tone_and_manner,
    }


@router.post("/brand-profile")
async def update_brand_profile(body: BrandProfileBody, x_client_id: str = Header()):
    """브랜드 프로필 저장 — 전달된 필드만 업데이트(나머지 유지)."""
    p = save_profile(
        x_client_id,
        brand_color=body.brand_color,
        brand_logo_key=body.brand_logo_key,
        tone_and_manner=body.tone_and_manner,
    )
    return {
        "saved": True,
        "brand_color": p.brand_color,
        "brand_logo_key": p.brand_logo_key,
        "tone_and_manner": p.tone_and_manner,
    }


@router.post("/logo")
async def upload_logo(
    x_client_id: str = Header(),
    file: UploadFile = File(...),
):
    """로고 이미지 업로드 → S3 저장 → 키 + presigned URL 반환."""
    ct = (file.content_type or "").split(";")[0].strip()
    if ct not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="PNG·JPEG·WebP·GIF 이미지만 업로드 가능합니다.")

    data = await file.read()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="로고 파일은 2MB 이하여야 합니다.")

    img = Image.open(io.BytesIO(data))
    if max(img.size) > 1024:
        raise HTTPException(
            status_code=400,
            detail=f"로고는 한 변 1024px 이하여야 합니다. (현재 {img.size[0]}×{img.size[1]})",
        )

    ext = _ALLOWED_IMAGE_TYPES[ct]
    key = brand_logo_key(x_client_id, ext)
    await upload_bytes(data, key, content_type=ct)
    save_profile(x_client_id, brand_logo_key=key)

    url = await presign_get(key)
    return {"key": key, "url": url}


class GenerationTaskResponse(BaseModel):
    generation_id: str
    stream_url: str


class CandidateSelectRequest(BaseModel):
    candidate_id: str


class PublishRequest(BaseModel):
    candidate_id: str
    caption: str = ""


@router.get("/instagram-status")
async def instagram_status():
    """Meta 자격증명 로드 상태 진단 (토큰 값은 노출하지 않음)."""
    from dotenv import dotenv_values

    from core.config import settings as cached
    from domain.generator.adapters.instagram import build_publisher, load_meta_credentials

    token, ig_account_id, api_version = load_meta_credentials()
    publisher = build_publisher()
    env_path = _backend_env_path()
    file_vals = dotenv_values(env_path) if env_path.exists() else {}
    file_token = (file_vals.get("META_ACCESS_TOKEN") or "").strip()
    proc_token = os.environ.get("META_ACCESS_TOKEN") or ""
    return {
        "publisher": type(publisher).__name__,
        "cwd": os.getcwd(),
        "env_file": str(env_path),
        "env_file_exists": env_path.exists(),
        "file_token_len": len(file_token),
        "process_token_len": len(proc_token.strip()),
        "active_token_len": len(token or ""),
        "tokens_in_sync": len(file_token) == len(token or ""),
        "ig_account_id_prefix": (ig_account_id or "")[:6] or None,
        "api_version": api_version,
        # Settings 캐시 상태 (새 변수명 기준)
        "cached_meta_token_set": bool(cached.meta_access_token),
        "cached_meta_instagram_account_id_set": bool(cached.meta_instagram_account_id),
        "cached_meta_app_id_set": bool(cached.meta_app_id),
        "cached_meta_page_id_set": bool(cached.meta_page_id),
        "cached_meta_ad_account_id_set": bool(cached.meta_ad_account_id),
    }


def _backend_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


@router.get("/langsmith-status")
async def langsmith_status():
    """LangSmith 트레이싱 로드 상태 진단 (API 키 값은 노출하지 않음)."""
    from core.config import settings as cfg

    try:
        from langsmith.utils import tracing_is_enabled

        enabled = tracing_is_enabled()
    except Exception:  # noqa: BLE001 — 진단 목적, SDK 버전차 방어
        enabled = None

    key = cfg.LANGSMITH_API_KEY
    return {
        "tracing_enabled": enabled,
        "api_key_loaded": bool(key),
        "api_key_len": len(key or ""),
        "project": (
            os.environ.get("LANGSMITH_PROJECT")
            or os.environ.get("LANGCHAIN_PROJECT")
            or cfg.LANGSMITH_PROJECT
        ),
        "endpoint": cfg.LANGSMITH_ENDPOINT,
        "env_tracing": (
            os.environ.get("LANGSMITH_TRACING") or os.environ.get("LANGCHAIN_TRACING_V2")
        ),
    }


# ── graph 기반 비동기 생성 엔드포인트 ────────────────────────────────────────


@router.post("/generations", response_model=GenerationTaskResponse)
async def create_generation(
    body: GenerationCreateRequest,
    current_user: User = Depends(get_current_user),
):
    generation_id = await generator_service.start_generation(body, created_by=current_user.id)
    return GenerationTaskResponse(
        generation_id=generation_id,
        stream_url=f"/api/generator/generations/{generation_id}/stream",
    )


@router.get("/generations")
async def list_generations(limit: int = 20):
    return {"generations": await generator_service.list_generations(limit=limit)}


@router.get("/generations/{generation_id}/stream")
async def stream_generation(generation_id: str):
    return StreamingResponse(
        generator_service.stream_events(generation_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/generations/{generation_id}")
async def get_generation(generation_id: str):
    detail = await generator_service.get_detail(generation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    return detail


@router.post("/generations/{generation_id}/select")
async def select_candidate(generation_id: str, body: CandidateSelectRequest):
    ok = await generator_service.select_candidate(generation_id, body.candidate_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Candidate not found in this generation")
    return {"generation_id": generation_id, "selected_candidate_id": body.candidate_id}


@router.post("/generations/{generation_id}/advertise")
async def advertise_candidate(generation_id: str, body: AdvertiseRequest):
    """사용자 승인 액션 — 선택된 후보를 Meta Marketing API로 광고 집행 (기본 PAUSED)."""
    result = await generator_service.advertise_candidate(generation_id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="Candidate not found in this generation")
    return result


@router.post("/generations/{generation_id}/publish")
async def publish_candidate(generation_id: str, body: PublishRequest):
    """사용자 승인 액션 — 선택된 후보를 Instagram에 게시한다."""
    result = await generator_service.publish_candidate(
        generation_id, body.candidate_id, body.caption
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Candidate not found in this generation")
    if result.get("error") == "selected_candidate_only":
        raise HTTPException(
            status_code=400, detail="선택된 후보만 게시할 수 있습니다. 먼저 후보를 선택하세요."
        )
    return result
