# 광고 제품 카테고리 마스터(categories/kinds) 조회 — ORM 없는 읽기전용 테이블 raw SQL.
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 업종 대분류 ↔ NICE 상품분류 45류(kinds)를 매핑 테이블로 조인. service_class = kinds.id.
_CATEGORY_SQL = text(
    """
    SELECT c.id AS category_id, c.name, k.id AS kind_id, k.description
    FROM categories c
    JOIN category_kinds ck ON ck.category_id = c.id
    JOIN kinds k ON k.id = ck.kind_id
    ORDER BY c.id, k.id
    """
)


async def list_categories(session: AsyncSession) -> list[dict]:
    """대분류별 NICE 류 목록 — [{id, name, kinds: [{id, description}]}]. id 순 정렬."""
    rows = (await session.execute(_CATEGORY_SQL)).mappings().all()
    grouped: dict[int, dict] = {}
    for r in rows:
        cat = grouped.setdefault(
            r["category_id"],
            {"id": r["category_id"], "name": r["name"], "kinds": []},
        )
        cat["kinds"].append({"id": r["kind_id"], "description": r["description"]})
    return list(grouped.values())
