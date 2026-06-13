"""관리자 전용 API — ADMIN 역할만 접근 가능."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import require_admin
from core.db import get_db
from core.models import Organization, OrganizationMember, SimulationResult, User

router = APIRouter()


# ── Schemas ──────────────────────────────────


class PendingCompany(BaseModel):
    user_id: str
    user_name: str
    email: str
    company_name: str
    organization_id: str
    created_at: datetime


class UserRow(BaseModel):
    id: str
    email: str
    name: str
    role: str
    status: str
    created_at: datetime


class SimulationRow(BaseModel):
    id: str
    ad_id: str
    persona_count: int
    created_at: datetime


class GenerationRow(BaseModel):
    id: str
    status: str
    product_name: str | None
    created_by_name: str | None
    created_at: datetime


class ChatRow(BaseModel):
    id: str
    project_id: str | None
    message_count: int
    created_at: datetime


# ── COMPANY 승인 ──────────────────────────────


@router.get("/pending-companies", response_model=list[PendingCompany])
async def list_pending_companies(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """승인 대기 중인 COMPANY 계정 목록."""
    rows = await db.execute(
        select(User, Organization)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .where(User.role == "COMPANY", User.status == "PENDING")
    )
    result = []
    for user, org in rows.all():
        result.append(
            PendingCompany(
                user_id=str(user.id),
                user_name=user.name,
                email=user.email,
                company_name=org.name,
                organization_id=str(org.id),
                created_at=user.created_at,
            )
        )
    return result


@router.post("/approve-company/{user_id}")
async def approve_company(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """COMPANY 계정 승인 — user.status + org.status → ACTIVE."""
    user = await db.scalar(select(User).where(User.id == user_id, User.role == "COMPANY"))
    if not user:
        raise HTTPException(status_code=404, detail="해당 COMPANY 유저를 찾을 수 없습니다.")

    member = await db.scalar(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    )
    if not member:
        raise HTTPException(status_code=404, detail="조직 멤버 정보를 찾을 수 없습니다.")

    org = await db.scalar(select(Organization).where(Organization.id == member.organization_id))
    if not org:
        raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다.")

    user.status = "ACTIVE"
    org.status = "ACTIVE"
    return {"ok": True}


@router.post("/reject-company/{user_id}")
async def reject_company(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """COMPANY 계정 반려."""
    user = await db.scalar(select(User).where(User.id == user_id, User.role == "COMPANY"))
    if not user:
        raise HTTPException(status_code=404, detail="해당 COMPANY 유저를 찾을 수 없습니다.")
    user.status = "REJECTED"
    return {"ok": True}


# ── 전체 유저 목록 ────────────────────────────


@router.get("/users", response_model=list[UserRow])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = await db.execute(select(User).order_by(User.created_at.desc()))
    return [
        UserRow(
            id=str(u.id),
            email=u.email,
            name=u.name,
            role=u.role,
            status=u.status,
            created_at=u.created_at,
        )
        for u in rows.scalars()
    ]


# ── 전체 시뮬레이션 내역 ──────────────────────


@router.get("/simulations", response_model=list[SimulationRow])
async def list_simulations(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = await db.execute(
        select(SimulationResult).order_by(SimulationResult.created_at.desc()).limit(limit)
    )
    return [
        SimulationRow(
            id=str(r.id), ad_id=str(r.ad_id), persona_count=r.persona_count, created_at=r.created_at
        )
        for r in rows.scalars()
    ]


# ── 전체 제너레이터 내역 ──────────────────────


@router.get("/generations", response_model=list[GenerationRow])
async def list_generations(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = await db.execute(
        text("""
            SELECT g.id, g.status, g.input, g.created_at, u.name AS created_by_name
            FROM ad_generations g
            LEFT JOIN users u ON u.id = g.created_by
            ORDER BY g.created_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    )
    return [
        GenerationRow(
            id=str(r.id),
            status=r.status,
            product_name=(r.input or {}).get("product_name") if r.input else None,
            created_by_name=r.created_by_name,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ── 전체 채팅 내역 ────────────────────────────


@router.get("/chats", response_model=list[ChatRow])
async def list_chats(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    from core.models import ChatSession

    rows = await db.execute(
        select(ChatSession).order_by(ChatSession.created_at.desc()).limit(limit)
    )
    return [
        ChatRow(
            id=str(r.id),
            project_id=str(r.project_id) if r.project_id else None,
            message_count=len(r.messages) if r.messages else 0,
            created_at=r.created_at,
        )
        for r in rows.scalars()
    ]
