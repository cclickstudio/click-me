"""프로젝트 CRUD API."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.db import get_db
from core.models import OrganizationMember, User

router = APIRouter()


async def _get_user_org_id(user: User, db: AsyncSession) -> str:
    member = await db.scalar(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    )
    if not member:
        raise HTTPException(status_code=404, detail="소속 조직을 찾을 수 없습니다.")
    return str(member.organization_id)


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectRow(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    created_by_name: str | None
    organization_name: str | None = None
    created_at: datetime


@router.get("", response_model=list[ProjectRow])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.upper() == "ADMIN":
        result = await db.execute(
            text("""
                SELECT p.id, p.name, p.description, p.status, p.created_at,
                       u.name AS created_by_name, o.name AS organization_name
                FROM projects p
                LEFT JOIN users u ON u.id = p.created_by
                LEFT JOIN organizations o ON o.id = p.organization_id
                WHERE p.status != 'DELETED'
                ORDER BY p.created_at DESC
            """),
        )
    else:
        org_id = await _get_user_org_id(current_user, db)
        result = await db.execute(
            text("""
                SELECT p.id, p.name, p.description, p.status, p.created_at,
                       u.name AS created_by_name, o.name AS organization_name
                FROM projects p
                LEFT JOIN users u ON u.id = p.created_by
                LEFT JOIN organizations o ON o.id = p.organization_id
                WHERE p.organization_id = :org_id AND p.status != 'DELETED'
                ORDER BY p.created_at DESC
            """),
            {"org_id": org_id},
        )
    return [
        ProjectRow(
            id=str(r.id),
            name=r.name,
            description=r.description,
            status=r.status,
            created_by_name=r.created_by_name,
            organization_name=r.organization_name,
            created_at=r.created_at,
        )
        for r in result
    ]


@router.post("", response_model=ProjectRow, status_code=201)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = await _get_user_org_id(current_user, db)
    result = await db.execute(
        text("""
            INSERT INTO projects (id, organization_id, name, description, status, created_by)
            VALUES (gen_random_uuid(), :org_id, :name, :description, 'ACTIVE', :created_by)
            RETURNING id, name, description, status, created_at
        """),
        {
            "org_id": org_id,
            "name": body.name,
            "description": body.description,
            "created_by": str(current_user.id),
        },
    )
    await db.commit()
    r = result.fetchone()
    return ProjectRow(
        id=str(r.id),
        name=r.name,
        description=r.description,
        status=r.status,
        created_by_name=current_user.name,
        created_at=r.created_at,
    )


@router.get("/{project_id}/simulations")
async def list_project_simulations(
    project_id: str,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.upper() == "ADMIN":
        result = await db.execute(
            text("""
                SELECT s.id, s.status, s.sample_size, s.created_at, u.name AS created_by_name
                FROM simulations s
                LEFT JOIN users u ON u.id = s.created_by
                JOIN ads a ON a.id = s.ad_id
                WHERE a.project_id = :project_id
                ORDER BY s.created_at DESC
                LIMIT :limit
            """),
            {"project_id": project_id, "limit": limit},
        )
    else:
        org_id = await _get_user_org_id(current_user, db)
        result = await db.execute(
            text("""
                SELECT s.id, s.status, s.sample_size, s.created_at, u.name AS created_by_name
                FROM simulations s
                LEFT JOIN users u ON u.id = s.created_by
                JOIN ads a ON a.id = s.ad_id
                JOIN projects p ON p.id = a.project_id
                WHERE p.id = :project_id AND p.organization_id = :org_id
                ORDER BY s.created_at DESC
                LIMIT :limit
            """),
            {"project_id": project_id, "org_id": org_id, "limit": limit},
        )
    return [
        {
            "id": str(r.id),
            "status": r.status,
            "sample_size": r.sample_size,
            "created_by_name": r.created_by_name,
            "created_at": r.created_at.isoformat(),
        }
        for r in result
    ]


@router.get("/{project_id}/generations")
async def list_project_generations(
    project_id: str,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.upper() == "ADMIN":
        result = await db.execute(
            text("""
                SELECT g.id, g.status, g.input, g.created_at, u.name AS created_by_name
                FROM ad_generations g
                LEFT JOIN users u ON u.id = g.created_by
                WHERE g.project_id = :project_id
                ORDER BY g.created_at DESC
                LIMIT :limit
            """),
            {"project_id": project_id, "limit": limit},
        )
    else:
        org_id = await _get_user_org_id(current_user, db)
        result = await db.execute(
            text("""
                SELECT g.id, g.status, g.input, g.created_at, u.name AS created_by_name
                FROM ad_generations g
                LEFT JOIN users u ON u.id = g.created_by
                JOIN projects p ON p.id = g.project_id
                WHERE p.id = :project_id AND p.organization_id = :org_id
                ORDER BY g.created_at DESC
                LIMIT :limit
            """),
            {"project_id": project_id, "org_id": org_id, "limit": limit},
        )
    return [
        {
            "id": str(r.id),
            "status": r.status,
            "product_name": (r.input or {}).get("product_name") if r.input else None,
            "created_by_name": r.created_by_name,
            "created_at": r.created_at.isoformat(),
        }
        for r in result
    ]


@router.get("/simulations/{simulation_id}")
async def get_simulation_detail(
    simulation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = await _get_user_org_id(current_user, db)
    result = await db.execute(
        text("""
            SELECT s.id, s.status, s.sample_size, s.created_at,
                   u.name AS created_by_name,
                   a.id AS ad_id, a.title AS ad_title,
                   p.id AS project_id, p.name AS project_name,
                   sr.distribution, sr.personas
            FROM simulations s
            LEFT JOIN users u ON u.id = s.created_by
            JOIN ads a ON a.id = s.ad_id
            JOIN projects p ON p.id = a.project_id
            LEFT JOIN simulation_results sr ON sr.ad_id = s.ad_id
            WHERE s.id = :sim_id AND p.organization_id = :org_id
        """),
        {"sim_id": simulation_id, "org_id": org_id},
    )
    r = result.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="시뮬레이션을 찾을 수 없습니다.")
    return {
        "id": str(r.id),
        "status": r.status,
        "sample_size": r.sample_size,
        "result": r.distribution,
        "persona_results": r.personas,
        "created_at": r.created_at.isoformat(),
        "created_by_name": r.created_by_name,
        "ad_id": str(r.ad_id),
        "ad_title": r.ad_title,
        "project_id": str(r.project_id),
        "project_name": r.project_name,
    }


@router.get("/generations/{generation_id}")
async def get_generation_detail(
    generation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from domain.generator.service import generator_service

    org_id = await _get_user_org_id(current_user, db)
    # 조직 소속 확인
    meta = await db.execute(
        text("""
            SELECT g.id, u.name AS created_by_name, p.id AS project_id, p.name AS project_name
            FROM ad_generations g
            LEFT JOIN users u ON u.id = g.created_by
            JOIN projects p ON p.id = g.project_id
            WHERE g.id = :gen_id AND p.organization_id = :org_id
        """),
        {"gen_id": generation_id, "org_id": org_id},
    )
    r = meta.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="제너레이터 내역을 찾을 수 없습니다.")

    # candidates + presigned image_url 포함 전체 상세 조회
    detail = await generator_service.get_detail(generation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="제너레이터 내역을 찾을 수 없습니다.")

    import logging
    logger = logging.getLogger("clickme")

    candidates = detail.get("candidates", [])
    logger.info(
        "generation detail: id=%s candidates=%d image_urls=%s",
        generation_id,
        len(candidates),
        [c.get("image_url") and "ok" or "null" for c in candidates],
    )

    detail["id"] = detail.get("generation_id", generation_id)  # 프론트 GenDetail.id 호환
    detail["created_by_name"] = r.created_by_name
    detail["project_id"] = str(r.project_id)
    detail["project_name"] = r.project_name
    inp = detail.get("input") or {}
    detail["product_name"] = inp.get("product_name")
    return detail


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = await _get_user_org_id(current_user, db)
    result = await db.execute(
        text("SELECT id, created_by, organization_id FROM projects WHERE id = :id"),
        {"id": project_id},
    )
    project = result.fetchone()
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    if str(project.organization_id) != org_id:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    if current_user.role == "USER" and str(project.created_by) != str(current_user.id):
        raise HTTPException(status_code=403, detail="본인이 생성한 프로젝트만 삭제할 수 있습니다.")

    await db.execute(
        text("UPDATE projects SET status = 'DELETED' WHERE id = :id"),
        {"id": project_id},
    )
    await db.commit()
    return {"ok": True}
