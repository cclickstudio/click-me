# 챗 플랫폼 read 툴 — 프로젝트/조직 현황 조회(read-only, 도메인 횡단).
"""general/컨시어지 답변용. projects 라우터를 거치지 않고 Project/Organization을 직접 읽는다
(읽기 전용이라 권한판정 없이 조회만 — 쓰기·권한 변경은 하지 않음).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.models import Organization, Project


def _row(p: Project, org: Organization | None) -> dict:
    return {
        "project_id": str(p.id),
        "name": p.name,
        "description": p.description,
        "status": p.status,
        "organization": org.name if org is not None else None,
    }


async def project_status(
    project_id: str | None = None,
    organization_id: str | None = None,
    limit: int = 10,
) -> dict:
    """프로젝트 현황 — project_id면 단건 상세, 아니면 (organization_id 필터) 최근 프로젝트 목록."""
    try:
        async with AsyncSessionLocal() as db:
            if project_id:
                try:
                    pid = uuid.UUID(project_id)
                except ValueError:
                    return {"error": "invalid_project_id"}
                p = await db.get(Project, pid)
                if p is None or p.deleted_at is not None:
                    return {"error": "not_found", "project_id": project_id}
                org = await db.get(Organization, p.organization_id) if p.organization_id else None
                return {"project": _row(p, org)}

            stmt = (
                select(Project)
                .where(Project.deleted_at.is_(None))
                .order_by(Project.created_at.desc())
                .limit(limit)
            )
            if organization_id:
                try:
                    oid = uuid.UUID(organization_id)
                except ValueError:
                    return {"error": "invalid_organization_id"}
                stmt = stmt.where(Project.organization_id == oid)
            rows = (await db.execute(stmt)).scalars().all()
            return {"projects": [_row(p, None) for p in rows], "count": len(rows)}
    except Exception as e:  # noqa: BLE001 — 조회 오류 표면화
        return {"error": "lookup_failed", "detail": str(e)}
