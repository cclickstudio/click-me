# 챗 생성(generator) read 툴 — 생성 결과·목록을 조회(read-only).
"""서브에이전트가 부르는 조회 함수. generator_service 모듈 함수를 감싸 요약·에러 표면화한다.

org_id(문자열 UUID)를 주면 그 조직 생성물만(멀티테넌시 격리). service는 uuid.UUID를 기대하므로
여기서 str→UUID로 변환한다(미변환 시 조인 0건=오답). org_id=None이면 전역(무인증/내부).
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from core.db import AsyncSessionLocal


async def gen_detail(generation_id: str, org_id: str | None = None) -> dict:
    """특정 생성 작업의 상세(상태·후보·QA·선택안). 없거나 타 org면 not_found."""
    from domain.generator.service.generator_service import get_detail

    try:
        oid = uuid.UUID(org_id) if org_id else None
        detail = await get_detail(generation_id, org_id=oid)
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


async def gen_list(limit: int = 10, org_id: str | None = None) -> dict:
    """최근 생성 작업 목록(generation_id·상태·상품명). org_id 주면 그 조직 생성물만(테넌트 격리)."""
    from domain.generator.service.generator_service import list_generations

    try:
        oid = uuid.UUID(org_id) if org_id else None
        rows = await list_generations(limit=limit, org_id=oid)
    except Exception as e:  # noqa: BLE001
        return {"error": "lookup_failed", "detail": str(e)}
    rows = rows or []
    return {"generations": rows, "count": len(rows)}


# 이름 검색 — generation은 input JSONB->>'product_name'에 이름 보유(시뮬 ads.title와 다름).
# org는 projects 조인 격리(ad_generations엔 org 컬럼 없음). sim_find 선례와 정합.
_GEN_FIND_SQL = """
SELECT g.id, g.status, g.input->>'product_name' AS product_name,
       g.created_at, u.name AS created_by_name
FROM ad_generations g
LEFT JOIN users u ON u.id = g.created_by
JOIN projects p ON p.id = g.project_id
WHERE g.deleted_at IS NULL
  AND (CAST(:org AS uuid) IS NULL OR p.organization_id = CAST(:org AS uuid))
  AND g.input->>'product_name' ILIKE :pattern
ORDER BY g.created_at DESC
LIMIT :limit
"""


async def gen_find_by_name(name: str, org_id: str | None = None, limit: int = 10) -> dict:
    """상품명 부분일치(ILIKE)로 생성물 검색 — 후보 목록 반환. org_id=None이면 전역."""
    if not name or not name.strip():
        return {"error": "need_name"}
    try:
        oid = uuid.UUID(org_id) if org_id else None
    except ValueError:
        return {"error": "invalid_organization_id"}
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    text(_GEN_FIND_SQL),
                    {
                        "org": str(oid) if oid else None,
                        "pattern": f"%{name.strip()}%",
                        "limit": limit,
                    },
                )
            ).all()
    except Exception as e:  # noqa: BLE001
        return {"error": "lookup_failed", "detail": str(e)}
    gens = [
        {
            "generation_id": str(r.id),
            "status": r.status,
            "product_name": r.product_name,
            "created_by_name": r.created_by_name,
            "created_at": r.created_at.isoformat() if r.created_at is not None else None,
        }
        for r in rows
    ]
    return {"generations": gens, "count": len(gens), "query": name.strip()}
