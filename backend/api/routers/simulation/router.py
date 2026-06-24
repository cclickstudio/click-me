# 시뮬레이션 전송 계층 — 광고(텍스트+이미지 파일) 입력 → 페르소나 반응·집계 산출.
#
# 실데이터 전용(실 Gemini). GEMINI_API_KEY 없으면 시작 시 오류(mock 폴백 제거).
# 광고 이미지는 multipart 파일 업로드로 받아 임시 저장 후 VLM 해석에 사용.
from __future__ import annotations

import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import get_db
from domain.simulation.adapters.ad_image_store import persist_ad_image
from domain.simulation.adapters.category_repo import list_categories
from domain.simulation.contracts.schemas import SimulationRunRequest
from domain.simulation.repositories.simulation_repository import SimulationRepository
from domain.simulation.service.analysis_view import to_analysis_payload
from domain.simulation.wiring import _ensure_env, build_simulation_service
from tools.storage.s3 import download_bytes

# 프록시 허용 S3 프리픽스 — 시뮬 광고 이미지만(오픈 프록시 방지)
_SIM_IMAGE_PREFIX = "simulation/"

logger = logging.getLogger("clickme")
router = APIRouter()

_ensure_env("GEMINI_API_KEY")  # .env에서 키 적재(실데이터 전용 — mock 폴백 없음)
if not os.environ.get("GEMINI_API_KEY"):
    raise RuntimeError("GEMINI_API_KEY 미설정 — 시뮬레이션은 실 Gemini 전용입니다(mock 제거됨).")
_USE_LLM_QA = os.getenv("SIM_LLM_QA", "0") == "1"
# settings 주입 → settings.database_url 있으면 DB 영속화 활성(완료 런을 9테이블에 저장).
_service = build_simulation_service(settings=settings, use_llm_qa=_USE_LLM_QA)
logger.info("Simulation service: real(Gemini) 모드 (LLM QA=%s)", _USE_LLM_QA)

_IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10MB


async def _save_upload(ad_image: UploadFile | None) -> tuple[str | None, str | None]:
    """업로드 광고 이미지를 S3에 영속화하고 (vlm_ref, s3_key)를 반환(미설정 시 로컬 폴백)."""
    if ad_image is None:
        return None, None
    data = await ad_image.read()
    if len(data) > _IMAGE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(최대 10MB)")
    return await persist_ad_image(data, ad_image.filename, ad_image.content_type)


def _build_request(
    *,
    ad_id: str,
    ad_content: str | None,
    ad_image_path: str | None,
    ad_image_key: str | None,
    ad_image_url: str | None,
    organization_id: str | None,
    project_id: str | None,
    target_filter: str | None,
    target_mode: str,
    sample_size: int,
    allocation: str,
    ad_title: str | None,
    product_category: str | None,
    ad_objective: str | None,
    service_class: int | None,
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
        ad_image_url=ad_image_path
        or ad_image_url,  # VLM 입력: 업로드(presigned/로컬) 우선, 없으면 URL
        ad_image_key=ad_image_key,  # S3 영구 식별자(업로드 시만) — DB 영속·재조회 presign 대상
        organization_id=organization_id,
        project_id=project_id,
        target_filter=tf,
        target_mode=target_mode,
        sample_size=sample_size,
        allocation=allocation,
        # 선언 의도(의도 교차검증 §3.5-3 기준) — 없으면 해당 차원 스킵.
        ad_title=ad_title,
        product_category=product_category,
        ad_objective=ad_objective,
        service_class=service_class,
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
    allocation: str = Form("auto"),  # auto=표본크기로 자동(300+ stratified). 명시값도 허용
    ad_title: str | None = Form(None),
    product_category: str | None = Form(None),
    ad_objective: str | None = Form(None),
    service_class: int | None = Form(None),
) -> dict:
    """비동기 시작 — run_id 반환. 진행률은 /stream, 결과는 /result."""
    ad_image_path, ad_image_key = await _save_upload(ad_image)
    req = _build_request(
        ad_id=ad_id,
        ad_content=ad_content,
        ad_image_path=ad_image_path,
        ad_image_key=ad_image_key,
        ad_image_url=ad_image_url,
        organization_id=organization_id,
        project_id=project_id,
        target_filter=target_filter,
        target_mode=target_mode,
        sample_size=sample_size,
        allocation=allocation,
        ad_title=ad_title,
        product_category=product_category,
        ad_objective=ad_objective,
        service_class=service_class,
    )
    run_id = await _service.start(req)
    return {
        "run_id": run_id,
        "mode": "real",
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
    allocation: str = Form("auto"),  # auto=표본크기로 자동(300+ stratified). 명시값도 허용
    ad_title: str | None = Form(None),
    product_category: str | None = Form(None),
    ad_objective: str | None = Form(None),
    service_class: int | None = Form(None),
    shape: str = "full",
) -> dict:
    """동기 실행 — 광고+세부사항 입력 → 끝까지 돌려 반응·루브릭·집계를 한 번에 반환.

    shape=analysis 면 분석팀 정리 스키마(중복 제거·평탄화)로 반환. 기본 full(원본).
    """
    ad_image_path, ad_image_key = await _save_upload(ad_image)
    req = _build_request(
        ad_id=ad_id,
        ad_content=ad_content,
        ad_image_path=ad_image_path,
        ad_image_key=ad_image_key,
        ad_image_url=ad_image_url,
        organization_id=organization_id,
        project_id=project_id,
        target_filter=target_filter,
        target_mode=target_mode,
        sample_size=sample_size,
        allocation=allocation,
        ad_title=ad_title,
        product_category=product_category,
        ad_objective=ad_objective,
        service_class=service_class,
    )
    try:
        result = await _service.run(req)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return to_analysis_payload(result) if shape == "analysis" else result


@router.get("/categories")
async def get_categories(session: AsyncSession = Depends(get_db)) -> list[dict]:
    """광고 제품 카테고리 — 업종 대분류별 NICE 상품분류(45류). 2단계 선택(대분류→세부)용."""
    return await list_categories(session)


@router.get("/image")
async def proxy_simulation_image(key: str) -> Response:
    """시뮬 광고 이미지 S3 프록시 — presigned URL을 브라우저에 노출하지 않기 위해 서버가 중계.

    simulation/ 프리픽스만 허용(버킷 내 임의 객체 열람·자격증명 노출 방지).
    """
    if ".." in key or not key.startswith(_SIM_IMAGE_PREFIX):
        raise HTTPException(status_code=403, detail="허용되지 않은 이미지 경로입니다.")
    try:
        data = await download_bytes(key)
    except Exception:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.") from None
    if key.endswith((".jpg", ".jpeg")):
        media = "image/jpeg"
    elif key.endswith(".webp"):
        media = "image/webp"
    elif key.endswith(".gif"):
        media = "image/gif"
    else:
        media = "image/png"
    return Response(content=data, media_type=media)


@router.get("/{run_id}/stream")
async def stream_simulation(run_id: str) -> StreamingResponse:
    """SSE — 노드별 진행률(progress)·완료(completed)·에러 이벤트 스트림."""
    return StreamingResponse(
        _service.stream_events(run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{run_id}/status")
async def get_simulation_status(run_id: str) -> dict:
    """실행 진행 상태(running/completed/failed). 새로고침 후 백그라운드 런 복원용.
    서버 인메모리 기준이라 모르는 run(재시작·완료소실)은 status=unknown."""
    st = _service.get_run_status(run_id)
    return st or {"run_id": run_id, "status": "unknown", "pct": 0, "stage": None}


@router.get("/{run_id}/result")
async def get_simulation_result(run_id: str) -> dict:
    """완료된 실행 결과(반응·루브릭·집계). 미완료/없음이면 404."""
    result = _service.get_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="결과 없음 — 미완료이거나 잘못된 run_id")
    return result


@router.get("/{run_id}/result/analysis")
async def get_simulation_result_analysis(run_id: str) -> dict:
    """완료된 실행 결과를 분석팀 정리 스키마(중복 제거·평탄화)로 반환. 없으면 404."""
    result = _service.get_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="결과 없음 — 미완료이거나 잘못된 run_id")
    return to_analysis_payload(result)


@router.get("/{simulation_id}/db-result")
async def get_simulation_db_result(
    simulation_id: str, session: AsyncSession = Depends(get_db)
) -> dict:
    """DB 영속 결과 재조회 — 새로고침·프로젝트 패널 재진입 시 SimRunResult 복원. 없으면 404."""
    try:
        sim_uuid = uuid.UUID(simulation_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"잘못된 simulation_id: {e}") from e
    result = await SimulationRepository(session).get_full_result(sim_uuid)
    if result is None:
        raise HTTPException(status_code=404, detail="결과 없음 — 잘못된 simulation_id")
    return result
