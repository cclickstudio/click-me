# 시뮬레이션 전송 계층 — 광고(텍스트+이미지 파일) 입력 → 페르소나 반응·집계 산출.
#
# 실데이터 전용(실 Gemini). GEMINI_API_KEY 없으면 시작 시 오류(mock 폴백 제거).
# 광고 이미지는 multipart 파일 업로드로 받아 임시 저장 후 VLM 해석에 사용.
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, require_user_org
from core.config import settings
from core.db import get_db
from core.models import User
from domain.simulation.adapters.category_repo import list_categories
from domain.simulation.contracts.schemas import SimulationRunRequest
from domain.simulation.repositories.simulation_repository import SimulationRepository
from domain.simulation.service.analysis_view import to_analysis_payload
from domain.simulation.wiring import _ensure_env, build_simulation_service

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
        ad_image_url=ad_image_path or ad_image_url,  # 업로드 파일 우선, 없으면 URL
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
    req = _build_request(
        ad_id=ad_id,
        ad_content=ad_content,
        ad_image_path=await _save_upload(ad_image),
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
    req = _build_request(
        ad_id=ad_id,
        ad_content=ad_content,
        ad_image_path=await _save_upload(ad_image),
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


@router.get("/{run_id}/result/analysis")
async def get_simulation_result_analysis(run_id: str) -> dict:
    """완료된 실행 결과를 분석팀 정리 스키마(중복 제거·평탄화)로 반환. 없으면 404."""
    result = _service.get_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="결과 없음 — 미완료이거나 잘못된 run_id")
    return to_analysis_payload(result)


_require_user_org = require_user_org  # core.auth 공용(없으면 409) — 라우터 복붙 제거


@router.get("/{simulation_id}/db-result")
async def get_simulation_db_result(
    simulation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """DB 영속 결과 재조회 — 새로고침·프로젝트 패널 재진입 시 SimRunResult 복원.

    로그인 org의 시뮬만 조회(멀티테넌시 격리). 다른 org·없음이면 404.
    """
    try:
        sim_uuid = uuid.UUID(simulation_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"잘못된 simulation_id: {e}") from e
    org_id = await _require_user_org(user, session)
    # 도메인 ORM import 없이 org 소유만 raw SQL로 검증(경계 유지).
    sim_org = await session.scalar(
        text("SELECT organization_id FROM simulations WHERE id = :sid"), {"sid": sim_uuid}
    )
    if sim_org is None or sim_org != org_id:
        raise HTTPException(status_code=404, detail="결과 없음 — 잘못된 simulation_id")
    result = await SimulationRepository(session).get_full_result(sim_uuid)
    if result is None:
        raise HTTPException(status_code=404, detail="결과 없음 — 잘못된 simulation_id")
    return result
