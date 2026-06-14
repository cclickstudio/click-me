"""광고 제너레이터 API — 생성 시작 / SSE 스트림 / 결과 조회 / 후보 선택 / 이력."""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from domain.generator.contracts.schemas import GenerationCreateRequest
from domain.generator.service import generator_service

router = APIRouter()


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

    token, ig_id, api_version = load_meta_credentials()
    publisher = build_publisher()
    env_path = _backend_env_path()
    file_token = (
        (dotenv_values(env_path).get("META_ACCESS_TOKEN") or "") if env_path.exists() else ""
    )
    proc_token = os.environ.get("META_ACCESS_TOKEN") or ""
    return {
        "publisher": type(publisher).__name__,
        "cwd": os.getcwd(),
        "env_file": str(env_path),
        "env_file_exists": env_path.exists(),
        "file_token_len": len(file_token.strip()),
        "process_token_len": len(proc_token.strip()),
        "active_token_len": len(token or ""),
        "tokens_in_sync": len(file_token.strip()) == len(token or ""),
        "fresh_ig_user_id_prefix": (ig_id or "")[:6] or None,
        "api_version": api_version,
        "cached_meta_token_set": bool(cached.meta_access_token),
        "cached_meta_ig_set": bool(cached.meta_ig_user_id),
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


@router.post("/generations", response_model=GenerationTaskResponse)
async def create_generation(body: GenerationCreateRequest):
    generation_id = await generator_service.start_generation(body)
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
