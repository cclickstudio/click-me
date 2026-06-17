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


# ── 하드 삭제 헬퍼 ────────────────────────────────
# 대부분의 FK가 NO ACTION이라 DB가 자동 cascade하지 않는다.
# 자식 테이블을 부모보다 먼저, FK 순서대로 직접 삭제해야 한다.


async def _purge_simulations(db: AsyncSession, sim_ids_sql: str, params: dict) -> None:
    """sim_ids_sql(시뮬레이션 id 서브쿼리)에 해당하는 시뮬과 모든 자식 레코드를 삭제."""
    stmts = [
        f"DELETE FROM persona_debate_utterances WHERE debate_id IN "
        f"(SELECT id FROM persona_debates WHERE simulation_id IN ({sim_ids_sql}))",
        f"DELETE FROM persona_debate_participants WHERE debate_id IN "
        f"(SELECT id FROM persona_debates WHERE simulation_id IN ({sim_ids_sql}))",
        f"DELETE FROM persona_debates WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM recommendations WHERE simulation_id IN ({sim_ids_sql}) "
        f"OR diagnosis_id IN (SELECT id FROM diagnoses WHERE simulation_id IN ({sim_ids_sql}))",
        f"DELETE FROM diagnoses WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM persona_responses WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM reports WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM simulation_aggregates WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM simulation_comparisons "
        f"WHERE simulation_a_id IN ({sim_ids_sql}) OR simulation_b_id IN ({sim_ids_sql})",
        f"DELETE FROM simulations WHERE id IN ({sim_ids_sql})",
    ]
    for s in stmts:
        await db.execute(text(s), params)


async def _purge_ads(db: AsyncSession, ad_ids_sql: str, params: dict) -> None:
    """광고와 자식 레코드를 삭제. (시뮬은 먼저 _purge_simulations로 제거할 것)"""
    stmts = [
        f"DELETE FROM simulation_results WHERE ad_id IN ({ad_ids_sql})",
        f"DELETE FROM ad_embeddings WHERE ad_id IN ({ad_ids_sql})",
        f"DELETE FROM rubric_scores WHERE ad_analysis_id IN "
        f"(SELECT id FROM ad_analyses WHERE ad_id IN ({ad_ids_sql}))",
        f"DELETE FROM ad_analyses WHERE ad_id IN ({ad_ids_sql})",
        f"DELETE FROM ads WHERE id IN ({ad_ids_sql})",
    ]
    for s in stmts:
        await db.execute(text(s), params)


async def _purge_generations(db: AsyncSession, gen_ids_sql: str, params: dict) -> None:
    """생성 요청 삭제. candidates는 FK CASCADE로 자동, publish_logs는 직접 삭제."""
    await db.execute(
        text(f"DELETE FROM ad_publish_logs WHERE generation_id IN ({gen_ids_sql})"), params
    )
    await db.execute(text(f"DELETE FROM ad_generations WHERE id IN ({gen_ids_sql})"), params)


async def _purge_project(db: AsyncSession, project_id: str) -> None:
    """프로젝트 1건과 하위 광고·시뮬·생성·채팅을 전부 하드 삭제."""
    p = {"pid": project_id}
    await _purge_simulations(
        db,
        "SELECT id FROM simulations WHERE ad_id IN (SELECT id FROM ads WHERE project_id = :pid)",
        p,
    )
    await db.execute(text("DELETE FROM simulation_comparisons WHERE project_id = :pid"), p)
    await _purge_ads(db, "SELECT id FROM ads WHERE project_id = :pid", p)
    await _purge_generations(db, "SELECT id FROM ad_generations WHERE project_id = :pid", p)
    await db.execute(text("DELETE FROM chat_sessions WHERE project_id = :pid"), p)
    await db.execute(text("DELETE FROM projects WHERE id = :pid"), p)


def _days_left(dt: datetime | None, days: int = 30) -> int | None:
    if dt is None:
        return None
    return max(0, days - (datetime.utcnow() - dt).days)


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
                WHERE p.status != 'DELETED' AND p.deleted_at IS NULL
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
                WHERE p.organization_id = :org_id AND p.status != 'DELETED' AND p.deleted_at IS NULL
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
                WHERE a.project_id = :project_id AND s.deleted_at IS NULL
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
                WHERE p.id = :project_id AND p.organization_id = :org_id AND s.deleted_at IS NULL
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
                WHERE g.project_id = :project_id AND g.deleted_at IS NULL
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
                WHERE p.id = :project_id AND p.organization_id = :org_id AND g.deleted_at IS NULL
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
            SELECT s.id, s.status, s.sample_size, s.created_at, s.deleted_at,
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
        "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
    }


@router.delete("/simulations/{simulation_id}")
async def delete_simulation(
    simulation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """시뮬레이션 1건 soft delete(휴지통 이동). 30일 후 _purge_expired_trash가 영구 삭제."""
    if current_user.role.upper() == "ADMIN":
        exists = await db.scalar(
            text("SELECT 1 FROM simulations WHERE id = :id"), {"id": simulation_id}
        )
    else:
        org_id = await _get_user_org_id(current_user, db)
        exists = await db.scalar(
            text("SELECT 1 FROM simulations WHERE id = :id AND organization_id = :org"),
            {"id": simulation_id, "org": org_id},
        )
    if not exists:
        raise HTTPException(status_code=404, detail="시뮬레이션을 찾을 수 없습니다.")

    await db.execute(
        text("UPDATE simulations SET deleted_at = now() WHERE id = :id"), {"id": simulation_id}
    )
    await db.commit()
    return {"ok": True}


@router.post("/simulations/{simulation_id}/restore")
async def restore_simulation(
    simulation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.upper() == "ADMIN":
        ok = await _restore(db, "simulations", simulation_id, "", {})
    else:
        org_id = await _get_user_org_id(current_user, db)
        ok = await _restore(
            db,
            "simulations",
            simulation_id,
            " AND organization_id = :org AND deleted_at > now() - interval '30 days'",
            {"org": org_id},
        )
    if not ok:
        raise HTTPException(status_code=404, detail="시뮬레이션을 찾을 수 없습니다.")
    await db.commit()
    return {"ok": True}


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
            SELECT g.id, g.deleted_at, u.name AS created_by_name,
                   p.id AS project_id, p.name AS project_name
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
    detail["deleted_at"] = r.deleted_at.isoformat() if r.deleted_at else None
    inp = detail.get("input") or {}
    detail["product_name"] = inp.get("product_name")
    return detail


@router.delete("/generations/{generation_id}")
async def delete_generation(
    generation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """제너레이터 내역 1건 soft delete(휴지통 이동). 30일 후 영구 삭제."""
    if current_user.role.upper() == "ADMIN":
        ok = await db.scalar(
            text("SELECT 1 FROM ad_generations WHERE id = :id"), {"id": generation_id}
        )
    else:
        org_id = await _get_user_org_id(current_user, db)
        ok = await db.scalar(
            text("""
                SELECT 1 FROM ad_generations g
                JOIN projects p ON p.id = g.project_id
                WHERE g.id = :id AND p.organization_id = :org
            """),
            {"id": generation_id, "org": org_id},
        )
    if not ok:
        raise HTTPException(status_code=404, detail="제너레이터 내역을 찾을 수 없습니다.")

    await db.execute(
        text("UPDATE ad_generations SET deleted_at = now() WHERE id = :id"), {"id": generation_id}
    )
    await db.commit()
    return {"ok": True}


@router.post("/generations/{generation_id}/restore")
async def restore_generation(
    generation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.upper() == "ADMIN":
        ok = await db.scalar(
            text("UPDATE ad_generations SET deleted_at = NULL WHERE id = :id RETURNING id"),
            {"id": generation_id},
        )
    else:
        org_id = await _get_user_org_id(current_user, db)
        ok = await db.scalar(
            text("""
                UPDATE ad_generations SET deleted_at = NULL
                WHERE id = :id
                  AND project_id IN (SELECT id FROM projects WHERE organization_id = :org)
                  AND deleted_at > now() - interval '30 days'
                RETURNING id
            """),
            {"id": generation_id, "org": org_id},
        )
    if not ok:
        raise HTTPException(status_code=404, detail="제너레이터 내역을 찾을 수 없습니다.")
    await db.commit()
    return {"ok": True}


@router.get("/trash")
async def list_trash(
    org_id: str | None = None,
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """휴지통 — soft delete된 프로젝트·시뮬·제너.

    영구 삭제는 하지 않는다(soft delete 유지). 단 COMPANY/USER에게는 30일 이내
    항목만 보이고, ADMIN은 30일이 지난 항목까지 전부 본다.
    """
    is_admin = current_user.role.upper() == "ADMIN"
    scope = org_id if is_admin else await _get_user_org_id(current_user, db)

    def _filter(alias: str) -> str:
        w = f"{alias}.deleted_at IS NOT NULL"
        if not is_admin:
            w += f" AND {alias}.deleted_at > now() - interval '30 days'"
        return w

    proj_w, sim_w, gen_w = _filter("p"), _filter("s"), _filter("g")
    params: dict = {}
    if scope:
        proj_w += " AND p.organization_id = :org"
        sim_w += " AND s.organization_id = :org"
        gen_w += " AND p.organization_id = :org"
        params = {"org": scope}
    if project_id:
        # 특정 프로젝트 휴지통 — 그 프로젝트 소속 시뮬/제너만(삭제된 프로젝트 목록은 제외)
        sim_w += " AND a.project_id = :project"
        gen_w += " AND g.project_id = :project"
        params["project"] = project_id

    projects = (
        []
        if project_id
        else await db.execute(
            text(f"""
                SELECT p.id, p.name, p.deleted_at, o.name AS org_name
                FROM projects p
                LEFT JOIN organizations o ON o.id = p.organization_id
                WHERE {proj_w}
                ORDER BY p.deleted_at DESC
            """),
            params,
        )
    )
    sims = await db.execute(
        text(f"""
            SELECT s.id, s.deleted_at, a.title AS ad_title
            FROM simulations s
            LEFT JOIN ads a ON a.id = s.ad_id
            WHERE {sim_w}
            ORDER BY s.deleted_at DESC
        """),
        params,
    )
    gens = await db.execute(
        text(f"""
            SELECT g.id, g.deleted_at, g.input
            FROM ad_generations g
            LEFT JOIN projects p ON p.id = g.project_id
            WHERE {gen_w}
            ORDER BY g.deleted_at DESC
        """),
        params,
    )
    return {
        "projects": [
            {
                "id": str(r.id),
                "name": r.name,
                "org_name": r.org_name,
                "deleted_at": r.deleted_at.isoformat(),
                "days_left": _days_left(r.deleted_at),
            }
            for r in projects
        ],
        "simulations": [
            {
                "id": str(r.id),
                "ad_title": r.ad_title,
                "deleted_at": r.deleted_at.isoformat(),
                "days_left": _days_left(r.deleted_at),
            }
            for r in sims
        ],
        "generations": [
            {
                "id": str(r.id),
                "product_name": (r.input or {}).get("product_name") if r.input else None,
                "deleted_at": r.deleted_at.isoformat(),
                "days_left": _days_left(r.deleted_at),
            }
            for r in gens
        ],
    }


async def _restore(db: AsyncSession, table: str, item_id: str, org_sql: str, params: dict) -> bool:
    """deleted_at을 NULL로 되돌려 휴지통에서 복원. 권한 범위(org_sql)에 맞는 행만."""
    res = await db.execute(
        text(f"UPDATE {table} SET deleted_at = NULL WHERE id = :id{org_sql} RETURNING id"),
        {"id": item_id, **params},
    )
    return res.fetchone() is not None


@router.post("/{project_id}/restore")
async def restore_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.upper() == "ADMIN":
        ok = await _restore(db, "projects", project_id, "", {})
    else:
        org_id = await _get_user_org_id(current_user, db)
        ok = await _restore(
            db,
            "projects",
            project_id,
            " AND organization_id = :org AND deleted_at > now() - interval '30 days'",
            {"org": org_id},
        )
    if not ok:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    await db.commit()
    return {"ok": True}


class TrashAction(BaseModel):
    sim_ids: list[str] = []
    gen_ids: list[str] = []


async def _assert_project_access(db: AsyncSession, project_id: str, current_user: User) -> None:
    """프로젝트가 존재하고, (비ADMIN이면) 사용자 조직 소속인지 확인."""
    row = await db.execute(
        text("SELECT organization_id FROM projects WHERE id = :pid"), {"pid": project_id}
    )
    p = row.fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    if current_user.role.upper() != "ADMIN":
        org_id = await _get_user_org_id(current_user, db)
        if str(p.organization_id) != org_id:
            raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")


@router.post("/{project_id}/trash/restore")
async def restore_trash(
    project_id: str,
    body: TrashAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """프로젝트 휴지통 복원 — ids 지정 시 선택 복원, 비어 있으면 전체 복원."""
    await _assert_project_access(db, project_id, current_user)
    if body.sim_ids or body.gen_ids:
        if body.sim_ids:
            await db.execute(
                text(
                    "UPDATE simulations SET deleted_at = NULL "
                    "WHERE id = ANY(:ids) AND deleted_at IS NOT NULL"
                ),
                {"ids": body.sim_ids},
            )
        if body.gen_ids:
            await db.execute(
                text(
                    "UPDATE ad_generations SET deleted_at = NULL "
                    "WHERE id = ANY(:ids) AND deleted_at IS NOT NULL"
                ),
                {"ids": body.gen_ids},
            )
    else:
        await db.execute(
            text(
                "UPDATE simulations SET deleted_at = NULL "
                "WHERE ad_id IN (SELECT id FROM ads WHERE project_id = :pid) "
                "AND deleted_at IS NOT NULL"
            ),
            {"pid": project_id},
        )
        await db.execute(
            text(
                "UPDATE ad_generations SET deleted_at = NULL "
                "WHERE project_id = :pid AND deleted_at IS NOT NULL"
            ),
            {"pid": project_id},
        )
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/trash/purge")
async def purge_trash(
    project_id: str,
    body: TrashAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """프로젝트 휴지통 영구 삭제 — ids 지정 시 선택 삭제, 비어 있으면 전체 비우기."""
    await _assert_project_access(db, project_id, current_user)
    if body.sim_ids or body.gen_ids:
        if body.sim_ids:
            await _purge_simulations(
                db,
                "SELECT id FROM simulations WHERE id = ANY(:ids) AND deleted_at IS NOT NULL",
                {"ids": body.sim_ids},
            )
        if body.gen_ids:
            await _purge_generations(
                db,
                "SELECT id FROM ad_generations WHERE id = ANY(:ids) AND deleted_at IS NOT NULL",
                {"ids": body.gen_ids},
            )
    else:
        await _purge_simulations(
            db,
            "SELECT s.id FROM simulations s JOIN ads a ON a.id = s.ad_id "
            "WHERE a.project_id = :pid AND s.deleted_at IS NOT NULL",
            {"pid": project_id},
        )
        await _purge_generations(
            db,
            "SELECT id FROM ad_generations WHERE project_id = :pid AND deleted_at IS NOT NULL",
            {"pid": project_id},
        )
    await db.commit()
    return {"ok": True}


@router.get("/{project_id}", response_model=ProjectRow)
async def get_project(
    project_id: str,
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
                WHERE p.id = :id AND p.status != 'DELETED'
            """),
            {"id": project_id},
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
                WHERE p.id = :id AND p.organization_id = :org_id AND p.status != 'DELETED'
            """),
            {"id": project_id, "org_id": org_id},
        )
    r = result.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return ProjectRow(
        id=str(r.id),
        name=r.name,
        description=r.description,
        status=r.status,
        created_by_name=r.created_by_name,
        organization_name=r.organization_name,
        created_at=r.created_at,
    )


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """프로젝트 soft delete(휴지통 이동). 30일 후 _purge_expired_trash가 하위까지 영구 삭제."""
    result = await db.execute(
        text("SELECT id, created_by, organization_id FROM projects WHERE id = :id"),
        {"id": project_id},
    )
    project = result.fetchone()
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    if current_user.role.upper() != "ADMIN":
        org_id = await _get_user_org_id(current_user, db)
        if str(project.organization_id) != org_id:
            raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
        if current_user.role.upper() == "USER" and str(project.created_by) != str(current_user.id):
            raise HTTPException(
                status_code=403, detail="본인이 생성한 프로젝트만 삭제할 수 있습니다."
            )

    await db.execute(
        text("UPDATE projects SET deleted_at = now() WHERE id = :id"), {"id": project_id}
    )
    await db.commit()
    return {"ok": True}
