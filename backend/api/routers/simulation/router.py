# 시뮬레이션 전송 계층 — 광고(텍스트+이미지 파일) 입력 → 페르소나 반응·집계 산출.
#
# 실데이터 전용(실 Gemini). GEMINI_API_KEY 없으면 시작 시 오류(mock 폴백 제거).
# 광고 이미지는 multipart 파일 업로드로 받아 임시 저장 후 VLM 해석에 사용.
from __future__ import annotations

import json
import logging
import os
import uuid

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, optional_user, require_user_org
from core.config import settings
from core.db import get_db
from core.models import User
from domain.simulation.adapters.ad_image_store import persist_ad_image
from domain.simulation.adapters.category_repo import list_categories
from domain.simulation.contracts.schemas import SegmentSpec, SimulationRunRequest
from domain.simulation.repositories.simulation_repository import SimulationRepository
from domain.simulation.service.analysis_view import to_analysis_payload
from domain.simulation.wiring import _ensure_env, build_simulation_service
from tools.storage.s3 import download_bytes

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


@router.get("/check-image")
async def check_image(url: str, current_user: User | None = Depends(optional_user)) -> dict:
    """URL 이미지를 VLM이 읽을 수 있는지 사전 확인 — 백엔드가 직접 GET(VLM 해석과 동일 경로).

    브라우저 미리보기(클라이언트 fetch)와 달리 '서버 접근성 + 이미지 여부'를 검증한다.
    시뮬 VLM은 서버가 URL을 다운로드해 해석하므로, 여기 결과가 실제 읽기 가능 여부와 일치한다.
    """
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "reason": "http(s) 이미지 URL이 아니에요."}
    try:
        # VLM(_load_image)과 동일하게 리다이렉트를 따르지 않고 단건 GET(그 응답을 해석 입력으로 씀).
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception:  # noqa: BLE001 — 접근 불가·차단·타임아웃·4xx/5xx는 모두 '읽기 불가'
        return {"ok": False, "reason": "이미지를 가져오지 못했어요(접근 불가·차단·타임아웃)."}
    mime = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not mime.startswith("image/"):
        return {
            "ok": False,
            "reason": f"이미지 파일이 아니에요(타입 {mime or '알 수 없음'}).",
        }
    return {"ok": True, "mime": mime}


async def _save_upload(ad_image: UploadFile | None) -> tuple[str | None, str | None]:
    """업로드 광고 이미지를 S3에 영속화하고 (vlm_ref, s3_key)를 반환(미설정 시 로컬 폴백)."""
    if ad_image is None:
        return None, None
    data = await ad_image.read()
    if len(data) > _IMAGE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(최대 10MB)")
    return await persist_ad_image(data, ad_image.filename, ad_image.content_type)


def _require_ad_image(
    ad_image_path: str | None, ad_image_key: str | None, ad_image_url: str | None
) -> None:
    """광고 이미지 필수 — 파일 업로드나 URL 중 하나는 있어야 한다(개선 모드가 base로 재사용)."""
    if not (ad_image_path or ad_image_key or (ad_image_url and ad_image_url.strip())):
        raise HTTPException(
            status_code=422, detail="광고 이미지는 필수입니다(파일 업로드 또는 이미지 URL)."
        )


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
    from_campaign_id: str | None = None,
    analysis_mode: str = "synthetic",
    user: User | None = None,
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
        # 사용자 식별(LangSmith 사용자별 필터) — 인증 시에만 채움(비인증은 익명).
        user_id=str(user.id) if user else None,
        login_id=user.login_id if user else None,
        user_name=user.name if user else None,
        role=user.role if user else None,
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
        from_campaign_id=from_campaign_id,
        analysis_mode=analysis_mode,
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
    from_campaign_id: str | None = Form(None),  # 관리 탭 진입 시 — 완료 후 서버가 자동 링크
    analysis_mode: str = Form(
        "synthetic"
    ),  # synthetic(기본)/individual(표본1 강제). persona_set은 /compare
    current_user: User | None = Depends(optional_user),  # 인증 시 트레이스에 사용자 식별
) -> dict:
    """비동기 시작 — run_id 반환. 진행률은 /stream, 결과는 /result."""
    ad_image_path, ad_image_key = await _save_upload(ad_image)
    _require_ad_image(ad_image_path, ad_image_key, ad_image_url)
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
        from_campaign_id=from_campaign_id,
        analysis_mode=analysis_mode,
        user=current_user,
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
    analysis_mode: str = Form(
        "synthetic"
    ),  # synthetic(기본)/individual(표본1 강제). persona_set은 /compare
    shape: str = "full",
    current_user: User | None = Depends(optional_user),  # 인증 시 트레이스에 사용자 식별
) -> dict:
    """동기 실행 — 광고+세부사항 입력 → 끝까지 돌려 반응·루브릭·집계를 한 번에 반환.

    shape=analysis 면 분석팀 정리 스키마(중복 제거·평탄화)로 반환. 기본 full(원본).
    """
    ad_image_path, ad_image_key = await _save_upload(ad_image)
    _require_ad_image(ad_image_path, ad_image_key, ad_image_url)
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
        analysis_mode=analysis_mode,
        user=current_user,
    )
    try:
        result = await _service.run(req)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return to_analysis_payload(result) if shape == "analysis" else result


@router.post("/compare")
async def compare_simulation(
    segments: str = Form(
        ...
    ),  # JSON [{label, target_filter:{age_min,age_max,gender}, sample_size}]
    ad_id: str = Form(...),
    ad_content: str | None = Form(None),
    ad_image: UploadFile | None = File(None),
    ad_image_url: str | None = Form(None),
    ad_title: str | None = Form(None),
    product_category: str | None = Form(None),
    ad_objective: str | None = Form(None),
    service_class: int | None = Form(None),
    allocation: str = Form("auto"),
    project_id: str | None = Form(None),
    organization_id: str | None = Form(None),
    current_user: User | None = Depends(optional_user),  # 인증 시 트레이스에 사용자 식별
) -> dict:
    """persona_set 3-모드 — 세그먼트 배열마다 개별 시뮬을 돌려 대조. run_id 반환.

    진행률은 /stream(세그먼트 메타 포함), 결과는 /result(mode=persona_set 형태)로 조회한다.
    """
    try:
        raw = json.loads(segments)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"segments JSON 오류: {e}") from e
    if not isinstance(raw, list) or not raw:
        raise HTTPException(status_code=422, detail="segments는 비어있지 않은 배열이어야 합니다.")
    try:
        specs = [SegmentSpec(**s) for s in raw]
    except (ValidationError, TypeError) as e:
        raise HTTPException(status_code=422, detail=f"segments 항목 오류: {e}") from e
    ad_image_path, ad_image_key = await _save_upload(ad_image)
    _require_ad_image(ad_image_path, ad_image_key, ad_image_url)
    base_req = _build_request(
        ad_id=ad_id,
        ad_content=ad_content,
        ad_image_path=ad_image_path,
        ad_image_key=ad_image_key,
        ad_image_url=ad_image_url,
        organization_id=organization_id,
        project_id=project_id,
        target_filter=None,  # 세그먼트별 target_filter가 각 런에서 덮어씀
        target_mode="AUTO",
        sample_size=20,  # 세그먼트별 sample_size가 각 런에서 덮어씀
        allocation=allocation,
        ad_title=ad_title,
        product_category=product_category,
        ad_objective=ad_objective,
        service_class=service_class,
        analysis_mode="persona_set",
        user=current_user,
    )
    run_id = await _service.start_comparison(base_req, specs)
    return {
        "run_id": run_id,
        "mode": "persona_set",
        "stream_url": f"/api/simulation/{run_id}/stream",
        "result_url": f"/api/simulation/{run_id}/result",
    }


@router.get("/categories")
async def get_categories(session: AsyncSession = Depends(get_db)) -> list[dict]:
    """광고 제품 카테고리 — 업종 대분류별 NICE 상품분류(45류). 2단계 선택(대분류→세부)용."""
    return await list_categories(session)


@router.get("/panel/personas")
async def list_panel_personas(
    version: str = "panel-v1",
    gender: str | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    limit: int = 30,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Individual 모드 — 고정 패널에서 특정 페르소나를 지정 선택하기 위한 미리보기 목록."""
    from domain.simulation.repositories.panel_repository import PanelRepository

    items, total = await PanelRepository(session).list_personas(
        version,
        gender=gender,
        age_min=age_min,
        age_max=age_max,
        limit=min(max(limit, 1), 100),
        offset=max(offset, 0),
    )
    return {"items": items, "total": total}


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
    """진행 상태(RUNNING/COMPLETED/FAILED) — 다른 탭 이동 후 복귀·새로고침 시 SSE 재구독용.

    실행 자체는 asyncio.create_task라 이 라우트·SSE 연결과 무관하게 계속 돈다.
    run_id를 모르면(서버 재시작·완료 소실) 404 — 프론트는 복원 포기하고 폼으로 되돌린다.
    """
    status = _service.get_run_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return status


@router.get("/{run_id}/result")
async def get_simulation_result(run_id: str) -> dict:
    """완료된 실행 결과(반응·루브릭·집계). 미완료/없음이면 404.

    persona_set 런이면 서비스가 {mode:"persona_set", run_id, segments:[{label, target_filter,
    sample_size, result}]} 형태로 저장하므로 그대로 반환된다(synthetic/individual은 기존 그대로).
    """
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
    # ADMIN은 조직 무관 전체 열람(목록/상세 핸들러와 동일 정책). 그 외는 org 소유만 조회.
    if user.role.upper() != "ADMIN":
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


@router.get("/image")
async def proxy_ad_image(key: str) -> Response:
    """시뮬레이션 광고 이미지를 백엔드 프록시로 제공 — AWS 자격증명 노출 방지.

    simulation/ 프리픽스만 허용해 버킷 내 임의 객체 열람을 막는다(제너·채팅과 동일 패턴).
    proxy_url_for(ad_image_store)가 만든 /api/simulation/image?key=... 를 이 라우트가 받는다.
    """
    if ".." in key or not key.startswith("simulation/"):
        raise HTTPException(status_code=403, detail="허용되지 않은 이미지 경로입니다.")
    try:
        data = await download_bytes(key)
    except Exception:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.") from None
    content_type = "image/jpeg" if key.endswith((".jpg", ".jpeg")) else "image/png"
    return Response(content=data, media_type=content_type)
