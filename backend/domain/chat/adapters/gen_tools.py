# 챗 생성(generator) read 툴 — 생성 결과·목록을 조회(read-only).
"""서브에이전트가 부르는 조회 함수. generator_service 모듈 함수를 감싸 요약·에러 표면화한다."""

from __future__ import annotations


async def gen_detail(generation_id: str) -> dict:
    """특정 생성 작업의 상세(상태·후보 수·QA 통과·선택안). 없으면 {"error": "not_found"}."""
    from domain.generator.service.generator_service import get_detail

    try:
        detail = await get_detail(generation_id)
    except Exception as e:  # noqa: BLE001 — 조회 오류는 표면화(read tool 계약)
        return {"error": "lookup_failed", "detail": str(e)}
    if not detail:
        return {"error": "not_found", "generation_id": generation_id}

    candidates = detail.get("candidates") or []
    return {
        "generation_id": detail.get("generation_id", generation_id),
        "status": detail.get("status"),
        "product_name": (detail.get("input") or {}).get("product_name"),
        "candidate_count": len(candidates),
        "qa_passed": sum(1 for c in candidates if c.get("qa_passed")),
        "selected_candidate_id": detail.get("selected_candidate_id"),
        "detail": detail,
    }


async def gen_list(limit: int = 10) -> dict:
    """최근 생성 작업 목록(generation_id·상태·상품명)."""
    from domain.generator.service.generator_service import list_generations

    try:
        rows = await list_generations(limit=limit)
    except Exception as e:  # noqa: BLE001
        return {"error": "lookup_failed", "detail": str(e)}
    rows = rows or []
    return {"generations": rows, "count": len(rows)}
