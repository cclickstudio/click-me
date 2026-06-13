"""대시보드 집계 API."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.models import AdGeneration, SimulationResult

router = APIRouter()


class DashboardStats(BaseModel):
    total_simulations: int
    total_generations: int
    avg_purchase_intent: float | None


class RecentSimulation(BaseModel):
    id: str
    ad_id: str
    persona_count: int
    avg_intent: float | None
    created_at: datetime


class RecentGeneration(BaseModel):
    id: str
    status: str
    product_name: str | None
    created_at: datetime


@router.get("/stats", response_model=DashboardStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_sim = await db.scalar(select(func.count()).select_from(SimulationResult))
    total_gen = await db.scalar(select(func.count()).select_from(AdGeneration))

    rows = await db.execute(select(SimulationResult.distribution))
    distributions = rows.scalars().all()

    avg_intent: float | None = None
    if distributions:
        scores = []
        for dist in distributions:
            if isinstance(dist, dict):
                weighted = sum(int(k) * v for k, v in dist.items() if str(k).lstrip("-").isdigit())
                total = sum(dist.values())
                if total > 0:
                    scores.append(weighted / total)
        if scores:
            avg_intent = round(sum(scores) / len(scores), 2)

    return DashboardStats(
        total_simulations=total_sim or 0,
        total_generations=total_gen or 0,
        avg_purchase_intent=avg_intent,
    )


@router.get("/recent-simulations", response_model=list[RecentSimulation])
async def get_recent_simulations(limit: int = 5, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SimulationResult).order_by(SimulationResult.created_at.desc()).limit(limit)
    )
    rows = result.scalars().all()

    items = []
    for r in rows:
        dist = r.distribution or {}
        weighted = sum(int(k) * v for k, v in dist.items() if str(k).lstrip("-").isdigit())
        total = sum(dist.values()) if dist else 0
        avg = round(weighted / total, 2) if total > 0 else None
        items.append(
            RecentSimulation(
                id=str(r.id),
                ad_id=str(r.ad_id),
                persona_count=r.persona_count,
                avg_intent=avg,
                created_at=r.created_at,
            )
        )
    return items


@router.get("/recent-generations", response_model=list[RecentGeneration])
async def get_recent_generations(limit: int = 5, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AdGeneration).order_by(AdGeneration.created_at.desc()).limit(limit)
    )
    rows = result.scalars().all()

    return [
        RecentGeneration(
            id=str(r.id),
            status=r.status,
            product_name=(r.input or {}).get("product_name"),
            created_at=r.created_at,
        )
        for r in rows
    ]
