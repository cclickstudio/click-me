# 광고 생성 어시스턴트 결과조회 도구 — 저장된 생성 결과를 후보·전략 요약으로
"""숫자·사실(후보·전략·QA)은 여기(저장된 결과)서만 가져온다. 전략·원칙은 KB(retriever)로 분리."""

from __future__ import annotations

import uuid


async def list_generations(project_id: str, limit: int = 10) -> list[dict]:
    """프로젝트의 최근 광고 생성 목록(id·상품명·모드·상태·생성시각). 이름/최근으로 특정할 때 쓴다."""
    if not project_id:
        return []
    from sqlalchemy import text  # noqa: PLC0415

    from core.db import AsyncSessionLocal  # noqa: PLC0415

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text("""
                SELECT g.id, g.status, g.input, g.created_at
                FROM ad_generations g
                WHERE g.project_id = :pid AND g.deleted_at IS NULL
                ORDER BY g.created_at DESC
                LIMIT :limit
            """),
            {"pid": project_id, "limit": max(1, min(limit, 50))},
        )
    out = []
    for r in rows:
        inp = r.input or {}
        out.append(
            {
                "id": str(r.id),
                "title": inp.get("product_name") or "제목 없음",
                "mode": inp.get("mode", "create"),
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return out


async def fetch_generation_result(generation_id: str) -> dict:
    """generation_id로 저장된 생성 결과의 후보·전략·선택 요약. 없으면 error 키."""
    # lazy import — generator_service는 이미지 생성 파이프라인을 모듈 로드 시 끌어와 무겁다.
    from domain.generator.service import generator_service  # noqa: PLC0415

    detail = await generator_service.get_detail(generation_id)
    if detail is None:
        return {"error": "not_found"}
    cands = detail.get("candidates") or []
    return {
        "generation_id": detail.get("generation_id"),
        "status": detail.get("status"),
        "candidate_count": len(cands),
        "selected_candidate_id": detail.get("selected_candidate_id"),
        "candidates": [
            {
                "candidate_id": c.get("candidate_id"),
                "strategy": c.get("strategy"),
                "headline": (c.get("copy") or {}).get("headline"),
                "qa_passed": c.get("qa_passed"),
            }
            for c in cands
        ],
        "error_message": detail.get("error_message"),
    }


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    """str → UUID (실패·None이면 None) — created_by 전파용."""
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def run_generation(
    product_name: str,
    product_description: str,
    target_audience: str,
    campaign_objective: str = "conversion",
    project_id: str | None = None,
    created_by: str | None = None,
) -> dict:
    """채팅에서 광고 시안 생성을 시작한다(백그라운드). generation_id 반환.

    mode는 기본 CREATE, project_id 없으면 프로젝트 미귀속.
    생성은 오래 걸려 동기 대기하지 않고 generation_id만 돌려준다(결과는 추후 조회).
    """
    from domain.generator.contracts.schemas import GenerationCreateRequest  # noqa: PLC0415
    from domain.generator.service import generator_service  # noqa: PLC0415

    req = GenerationCreateRequest(
        product_name=product_name,
        product_description=product_description,
        target_audience=target_audience,
        campaign_objective=campaign_objective,
        project_id=project_id,
    )
    generation_id = await generator_service.start_generation(
        req, created_by=_parse_uuid(created_by)
    )
    return {
        "generation_id": generation_id,
        "stream_url": f"/api/generator/generations/{generation_id}/stream",
    }


async def start_improve_generation(
    gen_data: dict,
    project_id: str | None = None,
    created_by: str | None = None,
) -> dict:
    """개선 프리필(improve_context 산출)로 IMPROVE 생성을 즉시 시작한다(백그라운드).

    gen_data는 improve_gen_data_for_simulation 결과(chat GenFormWidget 제출 바디와 동일 매핑).
    """
    from domain.generator.contracts.schemas import GenerationCreateRequest  # noqa: PLC0415
    from domain.generator.service import generator_service  # noqa: PLC0415

    req = GenerationCreateRequest(
        mode="improve",
        project_id=project_id,
        product_name=gen_data.get("product_name") or "",
        simulation_summary=gen_data.get("simulation_summary"),
        plain_summary=gen_data.get("plain_summary"),
        improvement_direction=gen_data.get("improvement_direction") or None,
        existing_ad_s3_key=gen_data.get("existing_ad_s3_key"),
        product_cutout_s3_key=gen_data.get("product_cutout_s3_key"),
        fix_requests=gen_data.get("fix_requests"),
        campaign_objective=gen_data.get("campaign_objective") or "conversion",
    )
    generation_id = await generator_service.start_generation(
        req, created_by=_parse_uuid(created_by)
    )
    return {
        "generation_id": generation_id,
        "stream_url": f"/api/generator/generations/{generation_id}/stream",
    }
