# 시뮬레이션 전송 계층 — 광고(텍스트+이미지 파일) 입력 → 페르소나 반응·집계 산출.
#
# 서비스는 wiring이 조립한 단일 인스턴스. SIM_REAL=1 이면 실 Gemini, 아니면 Mock(기본, 무비용).
# 광고 이미지는 multipart 파일 업로드로 받아 임시 저장 후 VLM 해석에 사용.
from __future__ import annotations

import json
import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from domain.simulation.contracts.schemas import SimulationRunRequest
from domain.simulation.wiring import build_simulation_service

router = APIRouter()

_USE_MOCK = os.getenv("SIM_REAL", "0") != "1"  # 기본 Mock. 실 Gemini는 SIM_REAL=1
_USE_LLM_QA = os.getenv("SIM_LLM_QA", "0") == "1"
_service = build_simulation_service(use_mock=_USE_MOCK, use_llm_qa=_USE_LLM_QA)

_IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10MB


async def _save_upload(ad_image: UploadFile | None) -> str | None:
    """업로드된 광고 이미지를 임시 파일로 저장하고 경로 반환(VLM 입력용)."""
    if ad_image is None:
        return None
    data = await ad_image.read()
    if len(data) > _IMAGE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(최대 10MB)")
    suffix = os.path.splitext(ad_image.filename or "")[1] or ".png"
    fd, path = tempfile.mkstemp(prefix="clickme_ad_", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def _build_request(
    *,
    ad_id: str,
    ad_content: str | None,
    ad_image_path: str | None,
    ad_image_url: str | None,
    organization_id: str | None,
    project_id: str | None,
    target_filter: str | None,
    target_mode: str,
    sample_size: int,
    allocation: str,
) -> SimulationRunRequest:
    """multipart 폼 값들을 도메인 요청 DTO로 조립. target_filter는 JSON 문자열."""
    tf = None
    if target_filter:
        try:
            tf = json.loads(target_filter)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=422, detail=f"target_filter JSON 오류: {e}") from e
    return SimulationRunRequest(
        ad_id=ad_id,
        ad_content=ad_content,
        ad_image_url=ad_image_path or ad_image_url,  # 업로드 파일 우선, 없으면 URL
        organization_id=organization_id,
        project_id=project_id,
        target_filter=tf,
        target_mode=target_mode,
        sample_size=sample_size,
        allocation=allocation,
    )


@router.post("")
async def start_simulation(
    ad_id: str = Form(...),
    ad_content: str | None = Form(None),
    ad_image: UploadFile | None = File(None),
    ad_image_url: str | None = Form(None),
    organization_id: str | None = Form(None),
    project_id: str | None = Form(None),
    target_filter: str | None = Form(None),
    target_mode: str = Form("AUTO"),
    sample_size: int = Form(20),
    allocation: str = Form("proportional"),
) -> dict:
    """비동기 시작 — run_id 반환. 진행률은 /stream, 결과는 /result."""
    req = _build_request(
        ad_id=ad_id, ad_content=ad_content, ad_image_path=await _save_upload(ad_image),
        ad_image_url=ad_image_url, organization_id=organization_id, project_id=project_id,
        target_filter=target_filter, target_mode=target_mode, sample_size=sample_size,
        allocation=allocation,
    )
    run_id = await _service.start(req)
    return {
        "run_id": run_id,
        "mode": "mock" if _USE_MOCK else "real",
        "stream_url": f"/api/simulation/{run_id}/stream",
        "result_url": f"/api/simulation/{run_id}/result",
    }


@router.post("/run")
async def run_simulation(
    ad_id: str = Form(...),
    ad_content: str | None = Form(None),
    ad_image: UploadFile | None = File(None),
    ad_image_url: str | None = Form(None),
    organization_id: str | None = Form(None),
    project_id: str | None = Form(None),
    target_filter: str | None = Form(None),
    target_mode: str = Form("AUTO"),
    sample_size: int = Form(20),
    allocation: str = Form("proportional"),
) -> dict:
    """동기 실행 — 광고+세부사항 입력 → 끝까지 돌려 반응·루브릭·집계를 한 번에 반환."""
    req = _build_request(
        ad_id=ad_id, ad_content=ad_content, ad_image_path=await _save_upload(ad_image),
        ad_image_url=ad_image_url, organization_id=organization_id, project_id=project_id,
        target_filter=target_filter, target_mode=target_mode, sample_size=sample_size,
        allocation=allocation,
    )
    try:
        return await _service.run(req)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{run_id}/stream")
async def stream_simulation(run_id: str) -> StreamingResponse:
    """SSE — 노드별 진행률(progress)·완료(completed)·에러 이벤트 스트림."""
    return StreamingResponse(
        _service.stream_events(run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{run_id}/result")
async def get_simulation_result(run_id: str) -> dict:
    """완료된 실행 결과(반응·루브릭·집계). 미완료/없음이면 404."""
    result = _service.get_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="결과 없음 — 미완료이거나 잘못된 run_id")
    return result
