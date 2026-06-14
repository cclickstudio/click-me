"""광고 생성 서비스 — 파이프라인 실행, SSE 진행률, DB 영속화, 후보 선택."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress

from PIL import Image
from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.models import AdGeneration, AdGenerationCandidate, AdPublishLog
from domain.generator.adapters.instagram import build_publisher
from domain.generator.contracts.schemas import GenerationCreateRequest
from domain.generator.graph.pipeline import generation_graph
from tools.storage.s3 import download_bytes, presign_get, publish_key, upload_bytes

logger = logging.getLogger("clickme")

_tasks: dict[str, dict] = {}


async def start_generation(
    request: GenerationCreateRequest,
    created_by: uuid.UUID | None = None,
) -> str:
    """생성 파이프라인 시작 — DB 행 생성 후 백그라운드 실행, generation_id 반환."""
    generation_id = str(uuid.uuid4())
    project_uuid = None
    if request.project_id:
        with suppress(ValueError):
            project_uuid = uuid.UUID(request.project_id)

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

    _tasks[generation_id] = {"status": "pending", "events": []}
    asyncio.create_task(_run_pipeline(generation_id, request))
    return generation_id


async def _run_pipeline(generation_id: str, request: GenerationCreateRequest) -> None:
    store = _tasks[generation_id]

    def emit(event: dict) -> None:
        store["events"].append(event)

    try:
        store["status"] = "running"
        await _update_status(generation_id, "running")

        config = {
            "run_name": "AdGenerationPipeline",
            "metadata": {"generation_id": generation_id},
            "configurable": {"emit": emit},
        }
        initial_state = {
            "generation_id": generation_id,
            "request": request.model_dump(),
        }
        final_state = await generation_graph.ainvoke(initial_state, config=config)

        await _persist_results(generation_id, final_state)
        store["status"] = "completed"
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
                    image_prompt=candidate["image_prompt"],
                    s3_key=candidate["s3_key"],
                    qa_result=qa_result,
                    qa_passed=qa_result["passed"],
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


async def get_detail(generation_id: str) -> dict | None:
    """생성 결과 상세 — DB 기준 (서버 재시작 후에도 조회 가능)."""
    try:
        gid = uuid.UUID(generation_id)
    except ValueError:
        return None

    async with AsyncSessionLocal() as session:
        generation = await session.get(AdGeneration, gid)
        if generation is None:
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
                "image_url": await presign_get(candidate.s3_key) if candidate.s3_key else None,
                "qa_result": candidate.qa_result,
                "qa_passed": candidate.qa_passed,
                "explanation": candidate.explanation,
            }
        )

    return {
        "generation_id": str(generation.id),
        "status": generation.status,
        "input": generation.input,
        "product_analysis": generation.product_analysis,
        "strategies": generation.strategies,
        "selected_candidate_id": (
            str(generation.selected_candidate_id) if generation.selected_candidate_id else None
        ),
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


async def list_generations(limit: int = 20) -> list[dict]:
    """생성 이력 목록 (최신순)."""
    async with AsyncSessionLocal() as session:
        generations = (
            (
                await session.execute(
                    select(AdGeneration).order_by(AdGeneration.created_at.desc()).limit(limit)
                )
            )
            .scalars()
            .all()
        )

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
