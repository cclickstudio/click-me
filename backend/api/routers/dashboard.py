"""대시보드 집계 API."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, user_org_id
from core.db import get_db
from core.models import AdGeneration, Project, User

router = APIRouter()


class DashboardStats(BaseModel):
    total_simulations: int
    total_generations: int
    avg_purchase_intent: float | None


class RecentSimulation(BaseModel):
    id: str
    ad_id: str
    ad_title: str | None
    persona_count: int
    avg_intent: float | None
    status: str
    created_at: datetime


class RecentGeneration(BaseModel):
    id: str
    status: str
    product_name: str | None
    mode: str  # create | improve (input JSONB에서 읽음)
    format: str  # single | carousel(카드뉴스) — 생성/카드 배지 분기
    created_at: datetime


@router.get("/stats", response_model=DashboardStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    # 실제 시뮬은 simulations 테이블에 저장된다(구 simulation_results 아님).
    total_sim = await db.scalar(text("SELECT count(*) FROM simulations WHERE deleted_at IS NULL"))
    total_gen = await db.scalar(
        select(func.count()).select_from(AdGeneration).where(text("deleted_at IS NULL"))
    )
    avg_intent = await db.scalar(text("SELECT AVG(purchase_intent_avg) FROM simulation_aggregates"))

    return DashboardStats(
        total_simulations=total_sim or 0,
        total_generations=total_gen or 0,
        avg_purchase_intent=round(float(avg_intent), 2) if avg_intent is not None else None,
    )


@router.get("/recent-simulations", response_model=list[RecentSimulation])
async def get_recent_simulations(
    limit: int = 5,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ADMIN은 전역, 그 외는 자기 organization 내역만(org 없으면 빈 결과).
    is_admin = user.role.upper() == "ADMIN"
    org_id = None if is_admin else await user_org_id(user, db)
    if not is_admin and org_id is None:
        return []
    rows = await db.execute(
        text("""
            SELECT s.id, s.ad_id, s.sample_size, s.status, s.created_at,
                   a.title AS ad_title, sa.purchase_intent_avg
            FROM simulations s
            JOIN ads a ON a.id = s.ad_id
            JOIN projects p ON p.id = a.project_id
            LEFT JOIN simulation_aggregates sa ON sa.simulation_id = s.id
            WHERE s.deleted_at IS NULL
              AND (CAST(:org AS uuid) IS NULL OR p.organization_id = CAST(:org AS uuid))
            ORDER BY s.created_at DESC
            LIMIT :limit
        """),
        {"limit": limit, "org": str(org_id) if org_id else None},
    )
    return [
        RecentSimulation(
            id=str(r.id),
            ad_id=str(r.ad_id),
            ad_title=r.ad_title,
            persona_count=r.sample_size,
            avg_intent=round(float(r.purchase_intent_avg), 2)
            if r.purchase_intent_avg is not None
            else None,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/recent-generations", response_model=list[RecentGeneration])
async def get_recent_generations(
    limit: int = 5,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ADMIN은 전역, 그 외는 자기 organization 내역만(org 없으면 빈 결과).
    is_admin = user.role.upper() == "ADMIN"
    org_id = None if is_admin else await user_org_id(user, db)
    if not is_admin and org_id is None:
        return []
    stmt = select(AdGeneration).where(text("ad_generations.deleted_at IS NULL"))
    if not is_admin:
        stmt = stmt.join(Project, Project.id == AdGeneration.project_id).where(
            Project.organization_id == org_id
        )
    stmt = stmt.order_by(AdGeneration.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        RecentGeneration(
            id=str(r.id),
            status=r.status,
            product_name=(r.input or {}).get("product_name"),
            mode=(r.input or {}).get("mode", "create"),
            format=(r.input or {}).get("format", "single"),
            created_at=r.created_at,
        )
        for r in rows
    ]
