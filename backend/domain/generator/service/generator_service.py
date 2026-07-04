"""광고 생성 서비스 — graph 파이프라인 실행, SSE 진행률, DB 영속화, 후보 선택·게시.

생성/개선 모두 graph(LangGraph) 파이프라인으로 처리한다(GenerationCreateRequest.mode로 분기).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import uuid
import zipfile
from collections.abc import AsyncIterator
from contextlib import suppress
from urllib.parse import quote

from PIL import Image
from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.execution_log import record_execution
from core.models import (
    AdGeneration,
    AdGenerationCandidate,
    AdPublishLog,
    OrganizationMember,
    Project,
)
from core.tracing import make_trace_config
from domain.generator.adapters.instagram import build_publisher
from domain.generator.contracts.enums import AdStrategy, GenerationMode, TemplateType
from domain.generator.contracts.schemas import GenerationCreateRequest
from domain.generator.graph.pipeline import generation_graph
from domain.generator.pipeline.relayout import render_platform
from tools.storage.s3 import (
    candidate_base_key,
    download_bytes,
    presign_get,
    product_cutout_key,
    publish_key,
    temp_product_image_key,
    upload_bytes,
)

logger = logging.getLogger("clickme")

_tasks: dict[str, dict] = {}
_background_tasks: set[asyncio.Task] = set()


async def store_temp_image(data: bytes) -> str:
    """상품 이미지를 S3에 임시 저장하고 S3 키를 반환한다."""
    key = temp_product_image_key(str(uuid.uuid4()))
    await upload_bytes(data, key, content_type="image/png")
    return key


async def start_generation(
    request: GenerationCreateRequest,
    created_by: uuid.UUID | None = None,
    created_by_login: str | None = None,
    created_by_name: str | None = None,
    created_by_role: str | None = None,
) -> str:
    """생성 파이프라인 시작 — DB 행 생성 후 백그라운드 실행, generation_id 반환."""
    generation_id = str(uuid.uuid4())
    project_uuid = None
    if request.project_id:
        with suppress(ValueError):
            project_uuid = uuid.UUID(request.project_id)
    if project_uuid is None:
        logger.warning(
            "생성 요청에 project_id가 없음 — 프로젝트에 기록되지 않음: generation_id=%s",
            generation_id,
        )

    async with AsyncSessionLocal() as session:
        session.add(
            AdGeneration(
                id=uuid.UUID(generation_id),
                project_id=project_uuid,
                created_by=created_by,
                status="pending",
                input=request.model_dump(),
            )
        )
        await session.commit()

    # 상품 이미지 bytes를 task store에 주입 (pipeline이 state로 전달받음)
    product_image_bytes: bytes | None = None
    if request.product_image_temp_key:
        try:
            product_image_bytes = await download_bytes(request.product_image_temp_key)
        except Exception:
            logger.warning(
                "상품 이미지 S3 다운로드 실패, 상품 없이 진행: key=%s",
                request.product_image_temp_key,
            )

    _tasks[generation_id] = {
        "status": "pending",
        "events": [],
        "product_image_bytes": product_image_bytes,
    }
    task = asyncio.create_task(
        _run_pipeline(
            generation_id,
            request,
            created_by=created_by,
            created_by_login=created_by_login,
            created_by_name=created_by_name,
            created_by_role=created_by_role,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return generation_id


async def _run_pipeline(
    generation_id: str,
    request: GenerationCreateRequest,
    created_by: uuid.UUID | None = None,
    created_by_login: str | None = None,
    created_by_name: str | None = None,
    created_by_role: str | None = None,
) -> None:
    store = _tasks[generation_id]

    def emit(event: dict) -> None:
        store["events"].append(event)

    try:
        store["status"] = "running"
        await _update_status(generation_id, "running")

        config = make_trace_config(
            domain="generator",
            feature="generate",
            mode=request.mode.value,
            user_id=str(created_by) if created_by else "anonymous",
            login_id=created_by_login,
            user_name=created_by_name,
            role=created_by_role,
            ad_id=request.existing_ad_s3_key if request.existing_ad_s3_key else None,
            project_id=request.project_id,
            extra_metadata={"generation_id": generation_id},
            configurable={"emit": emit},
        )
        initial_state = {
            "generation_id": generation_id,
            "request": request.model_dump(),
        }
        product_image_bytes: bytes | None = store.pop("product_image_bytes", None)
        if product_image_bytes is not None:
            initial_state["product_image_bytes"] = product_image_bytes

        final_state = await generation_graph.ainvoke(initial_state, config=config)

        await _persist_results(generation_id, final_state)
        store["status"] = "completed"
        # 실행 확정 지점 롱텀(실행 히스토리) 적재 — UI·채팅·반복루프 모든 경로가 여기로 수렴.
        # 채팅 요청행(spawn_persist)과는 stage로 구분(요청/완료 2행 패턴). best-effort·비차단.
        improve = request.mode == GenerationMode.IMPROVE
        await record_execution(
            request.project_id,
            "generation",
            "run_improvement" if improve else "run_generation",
            f"광고 {'개선 ' if improve else ''}생성 완료 — {request.product_name} "
            f"시안 {len(final_state.get('candidates') or [])}개 "
            f"타깃 {request.target_audience} 목표 {request.campaign_objective}",
            payload={
                "stage": "completed",
                "generation_id": generation_id,
                "mode": request.mode.value,
                "product_name": request.product_name,
                "target_audience": request.target_audience,
                "campaign_objective": request.campaign_objective,
            },
            user_id=str(created_by) if created_by else None,
        )
        emit(
            {
                "event": "completed",
                "result_url": f"/api/generator/generations/{generation_id}",
            }
        )
    except Exception as exc:
        logger.exception("광고 생성 실패: generation_id=%s", generation_id)
        store["status"] = "failed"
        await _update_status(generation_id, "failed", error_message=str(exc))
        emit({"event": "error", "message": str(exc)})
    finally:
        pass


async def _update_status(generation_id: str, status: str, error_message: str | None = None) -> None:
    async with AsyncSessionLocal() as session:
        generation = await session.get(AdGeneration, uuid.UUID(generation_id))
        if generation is None:
            return
        generation.status = status
        if error_message is not None:
            generation.error_message = error_message
        await session.commit()


async def _persist_results(generation_id: str, final_state: dict) -> None:
    """파이프라인 최종 state를 DB에 영속화."""
    async with AsyncSessionLocal() as session:
        generation = await session.get(AdGeneration, uuid.UUID(generation_id))
        if generation is None:
            raise RuntimeError(f"AdGeneration 행이 없습니다: {generation_id}")

        generation.status = "completed"
        generation.product_analysis = final_state.get("product_analysis")
        generation.strategies = final_state.get("strategies")

        rows = zip(
            final_state["candidates"],
            final_state["qa_results"],
            final_state["explanations"],
            strict=True,
        )
        for candidate, qa_result, explanation in rows:
            session.add(
                AdGenerationCandidate(
                    id=uuid.UUID(candidate["candidate_id"]),
                    generation_id=uuid.UUID(generation_id),
                    idx=candidate["idx"],
                    strategy=candidate["strategy"],
                    template_id=candidate["template_id"],
                    copy=candidate["copy"],
                    image_prompt=candidate.get("image_prompt"),
                    s3_key=candidate["s3_key"],
                    qa_result=qa_result,
                    qa_passed=qa_result.get("overall_passed", False),
                    explanation=explanation,
                )
            )
        await session.commit()


async def stream_events(generation_id: str) -> AsyncIterator[str]:
    """SSE 이벤트 스트림 — simulation_service와 동일한 인메모리 누적 방식."""
    if generation_id not in _tasks:
        yield 'data: {"event": "error", "message": "Generation task not found"}\n\n'
        return

    sent = 0
    while True:
        store = _tasks[generation_id]
        events = store["events"]
        while sent < len(events):
            yield f"data: {json.dumps(events[sent], ensure_ascii=False)}\n\n"
            sent += 1

        if store["status"] in ("completed", "failed"):
            break

        await asyncio.sleep(0.5)

    async def _deferred_cleanup(gid: str) -> None:
        await asyncio.sleep(30)
        _tasks.pop(gid, None)

    cleanup = asyncio.create_task(_deferred_cleanup(generation_id))
    _background_tasks.add(cleanup)
    cleanup.add_done_callback(_background_tasks.discard)


# 기대성과 순위(G7) — QA 점수로 후보를 정렬·근거 한 줄 부여. DB 스키마 변경 없이 조회 시 산출.
# (이미지 모델은 카피 품질만 평가 가능 — 예측 CTR 환산 아님. 품질 신호 기반 상대 순위.)
_QA_STRENGTH_LABELS: dict[str, str] = {
    "target_fit": "타깃 적합",
    "readability": "가독성 우수",
    "cta_exists": "CTA 명확",
    "text_length": "분량 적정",
    "brand_consistency": "브랜드 일관",
    "duplicate_check": "중복 없음",
    "typo_check": "오탈자 없음",
}


def _candidate_quality(qa: object) -> tuple[float, list[str]]:
    """qa_result(JSONB) → (평균 품질점수 0~1, 강점 라벨 목록). 신호 없으면 (0, [])."""
    if not isinstance(qa, dict):
        return 0.0, []
    items = [(k, v) for k, v in qa.items() if isinstance(v, dict) and "score" in v]
    if not items:
        return 0.0, []
    avg = sum(float(v.get("score") or 0.0) for _, v in items) / len(items)
    strengths = [
        _QA_STRENGTH_LABELS[k]
        for k, v in sorted(items, key=lambda kv: kv[1].get("score") or 0.0, reverse=True)
        if k in _QA_STRENGTH_LABELS and (v.get("score") or 0.0) >= 0.99
    ][:2]
    return avg, strengths


def _rank_candidates(cands: list[dict]) -> list[dict]:
    """후보에 rank·quality_score·performance_summary를 부여하고 기대성과 높은 순으로 정렬한다.

    정렬 기준 — QA 통과 여부 → 평균 품질점수 → idx(안정). 동점이면 원래 순서 유지.
    근거 한 줄(performance_summary): 만점 QA 항목 상위 2개 강점 + 품질 점수.
    """

    def _key(c: dict) -> tuple[int, float, int]:
        score, _ = _candidate_quality(c.get("qa_result"))
        return (1 if c.get("qa_passed") else 0, score, -int(c.get("idx") or 0))

    ordered = sorted(cands, key=_key, reverse=True)
    for rank, c in enumerate(ordered, start=1):
        score, strengths = _candidate_quality(c.get("qa_result"))
        c["rank"] = rank
        c["quality_score"] = round(score, 3)
        pts = f"품질 {round(score * 100)}점"
        c["performance_summary"] = " · ".join([*strengths, pts]) if strengths else pts
    return ordered


async def get_detail(generation_id: str, org_id: uuid.UUID | None = None) -> dict | None:
    """생성 결과 상세 — DB 기준 (서버 재시작 후에도 조회 가능).

    org_id가 주어지면 해당 생성물의 프로젝트 org와 일치할 때만 반환(멀티테넌시 격리).
    org_id=None이면 검증 생략 — 내부 서비스 호출(from-candidate) 전용.
    """
    try:
        gid = uuid.UUID(generation_id)
    except ValueError:
        return None

    async with AsyncSessionLocal() as session:
        generation = await session.get(AdGeneration, gid)
        if generation is None:
            return None
        if org_id is not None:
            if generation.project_id is None:
                # 프로젝트 없는(improve 등) 생성물 — 생성자(created_by)의 org로 검증해 노출.
                if generation.created_by is None:
                    return None
                member_org = await session.scalar(
                    select(OrganizationMember.organization_id).where(
                        OrganizationMember.user_id == generation.created_by
                    )
                )
                if member_org != org_id:
                    return None
            else:
                project = await session.get(Project, generation.project_id)
                if project is None or project.organization_id != org_id:
                    return None

        candidates = (
            (
                await session.execute(
                    select(AdGenerationCandidate)
                    .where(AdGenerationCandidate.generation_id == gid)
                    .order_by(AdGenerationCandidate.idx)
                )
            )
            .scalars()
            .all()
        )
        publish_logs = (
            (
                await session.execute(
                    select(AdPublishLog)
                    .where(AdPublishLog.generation_id == gid)
                    .order_by(AdPublishLog.created_at.desc())
                )
            )
            .scalars()
            .all()
        )

    candidate_dicts = []
    for candidate in candidates:
        candidate_dicts.append(
            {
                "candidate_id": str(candidate.id),
                "idx": candidate.idx,
                "strategy": candidate.strategy,
                "template_id": candidate.template_id,
                "copy": candidate.copy,
                "s3_key": candidate.s3_key,
                "image_url": f"/api/generator/image?key={quote(candidate.s3_key, safe='')}"
                if candidate.s3_key
                else None,
                "qa_result": candidate.qa_result,
                "qa_passed": candidate.qa_passed,
                "explanation": candidate.explanation,
            }
        )

    # 기대성과 순위 부여(G7) — QA 점수 기준 정렬 + rank·근거 한 줄. 완료 상태에서만 의미 있음.
    candidate_dicts = _rank_candidates(candidate_dicts)

    _gen_input = generation.input or {}
    # 생성 모드에서 상품 이미지가 있었던 경우에만 누끼 키를 반환 (개선 모드 재사용을 위해)
    _cutout_s3_key: str | None = None
    if _gen_input.get("mode", "create") == "create" and _gen_input.get("product_image_temp_key"):
        _cutout_s3_key = product_cutout_key(str(generation.id))

    return {
        # D1 계약 버전 — management from-candidate 핸드오프가 검증(불일치 시 409).
        "schema_version": "1",
        "generation_id": str(generation.id),
        "status": generation.status,
        "input": generation.input,
        "product_analysis": generation.product_analysis,
        "strategies": generation.strategies,
        "selected_candidate_id": (
            str(generation.selected_candidate_id) if generation.selected_candidate_id else None
        ),
        "product_cutout_s3_key": _cutout_s3_key,
        "error_message": generation.error_message,
        "created_at": generation.created_at.isoformat(),
        "candidates": candidate_dicts,
        "publish_logs": [
            {
                "id": str(log.id),
                "candidate_id": str(log.candidate_id) if log.candidate_id else None,
                "platform": log.platform,
                "status": log.status,
                "ig_media_id": log.ig_media_id,
                "caption": log.caption,
                "error_message": log.error_message,
                "created_at": log.created_at.isoformat(),
            }
            for log in publish_logs
        ],
    }


async def download_zip(generation_id: str) -> bytes | None:
    """생성 결과의 모든 후보 이미지를 ZIP으로 묶어 bytes 반환. 없으면 None."""
    detail = await get_detail(generation_id)
    if detail is None:
        return None

    candidates = [c for c in detail["candidates"] if c.get("s3_key")]
    if not candidates:
        return None

    async def _fetch(s3_key: str) -> bytes:
        return await download_bytes(s3_key)

    images = await asyncio.gather(*[_fetch(c["s3_key"]) for c in candidates])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for candidate, data in zip(candidates, images, strict=True):
            filename = f"image_{candidate['idx'] + 1}.png"
            zf.writestr(filename, data)
    return buf.getvalue()


async def render_candidate(candidate_id: str, platform: str) -> bytes | None:
    """후보를 지정 플랫폼 사이즈로 리레이아웃해 PNG bytes 반환 (LLM 재호출 없음).

    base(텍스트 없는 원본)·카피·브랜드를 DB/S3에서 조회해 PIL로 재구성.
    base가 없으면(과거 생성물) None — 신규 생성물부터 지원.
    """
    try:
        cid = uuid.UUID(candidate_id)
    except ValueError:
        return None

    async with AsyncSessionLocal() as session:
        candidate = await session.get(AdGenerationCandidate, cid)
        if candidate is None:
            return None
        generation = await session.get(AdGeneration, candidate.generation_id)
        gen_input = (generation.input or {}) if generation else {}
        idx = candidate.idx
        gen_id = str(candidate.generation_id)
        copy = candidate.copy or {}
        template_id = candidate.template_id
        strat_raw = (candidate.strategy or {}).get("strategy_type")

    # strategy 복원 — 없거나 잘못된 값이면 None (box 폴백)
    try:
        strategy = AdStrategy(strat_raw) if strat_raw else None
    except ValueError:
        strategy = None

    try:
        base_bytes = await download_bytes(candidate_base_key(gen_id, idx))
    except Exception:
        return None  # base 없음(과거 생성물) → 리레이아웃 미지원

    logo_bytes: bytes | None = None
    logo_key = gen_input.get("brand_logo_s3_key")
    if logo_key:
        with suppress(Exception):
            logo_bytes = await download_bytes(logo_key)

    return render_platform(
        base_bytes,
        headline=copy.get("headline", ""),
        body=copy.get("body", ""),
        cta=copy.get("cta", ""),
        template=TemplateType(template_id),
        platform=platform,
        brand_color=gen_input.get("brand_color"),
        logo_bytes=logo_bytes,
        strategy=strategy,
    )


async def select_candidate(generation_id: str, candidate_id: str) -> bool:
    """사용자가 선택한 후보 저장 — 후보가 해당 생성에 속하는지 검증."""
    try:
        gid = uuid.UUID(generation_id)
        cid = uuid.UUID(candidate_id)
    except ValueError:
        return False

    async with AsyncSessionLocal() as session:
        candidate = await session.get(AdGenerationCandidate, cid)
        if candidate is None or candidate.generation_id != gid:
            return False
        generation = await session.get(AdGeneration, gid)
        if generation is None:
            return False
        generation.selected_candidate_id = cid
        await session.commit()
        return True


async def list_generations(limit: int = 20, org_id: uuid.UUID | None = None) -> list[dict]:
    """생성 이력 목록 (최신순). org_id가 주어지면 그 org 프로젝트 생성물만(멀티테넌시 격리)."""
    async with AsyncSessionLocal() as session:
        stmt = select(AdGeneration).order_by(AdGeneration.created_at.desc())
        if org_id is not None:
            # 프로젝트→org 조인으로 로그인 org 생성물만. 프로젝트 없는 생성물은 자동 제외.
            stmt = stmt.join(Project, AdGeneration.project_id == Project.id).where(
                Project.organization_id == org_id
            )
        generations = (await session.execute(stmt.limit(limit))).scalars().all()

    return [
        {
            "generation_id": str(g.id),
            "status": g.status,
            "product_name": (g.input or {}).get("product_name"),
            "selected_candidate_id": (
                str(g.selected_candidate_id) if g.selected_candidate_id else None
            ),
            "created_at": g.created_at.isoformat(),
        }
        for g in generations
    ]


def png_to_jpeg(png_bytes: bytes, quality: int = 90) -> bytes:
    """PNG → JPEG 변환 — Instagram Content Publishing은 JPEG만 공식 지원."""
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


async def publish_candidate(generation_id: str, candidate_id: str, caption: str) -> dict | None:
    """사용자 승인 후 Instagram 게시 — 선택된 후보만 허용, 이력 전체 기록 (계획서 19장)."""
    try:
        gid = uuid.UUID(generation_id)
        cid = uuid.UUID(candidate_id)
    except ValueError:
        return None

    async with AsyncSessionLocal() as session:
        generation = await session.get(AdGeneration, gid)
        candidate = await session.get(AdGenerationCandidate, cid)
        if generation is None or candidate is None or candidate.generation_id != gid:
            return None
        if generation.selected_candidate_id != cid:
            return {"error": "selected_candidate_only"}
        png_key = candidate.s3_key
        candidate_idx = candidate.idx

    # IG는 JPEG만 지원 — 게시용 변환본을 별도 키로 업로드 후 presigned URL 전달
    png_bytes = await download_bytes(png_key)
    jpeg_key = publish_key(generation_id, candidate_idx)
    await upload_bytes(png_to_jpeg(png_bytes), jpeg_key, content_type="image/jpeg")
    image_url = await presign_get(jpeg_key)

    publisher = build_publisher()
    outcome = await publisher.publish_image(image_url, caption)

    if outcome.mocked:
        status = "mocked"
    elif outcome.success:
        status = "published"
    else:
        status = "failed"

    async with AsyncSessionLocal() as session:
        session.add(
            AdPublishLog(
                generation_id=gid,
                candidate_id=cid,
                platform="instagram",
                status=status,
                ig_container_id=outcome.container_id,
                ig_media_id=outcome.media_id,
                caption=caption,
                request_payload={"image_url": image_url, "caption": caption},
                response_payload=outcome.raw,
                error_message=outcome.error,
            )
        )
        await session.commit()

    return {
        "generation_id": generation_id,
        "candidate_id": candidate_id,
        "status": status,
        "success": outcome.success,
        "mocked": outcome.mocked,
        "media_id": outcome.media_id,
        "error": outcome.error,
    }
