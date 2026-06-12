"""광고 제너레이터 API — 생성 시작 / SSE 스트림 / 결과 조회 / 후보 선택 / 이력."""

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
