"""기업(COMPANY) 전용 API — 소속 USER 승인/관리."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.db import get_db
from core.models import Organization, OrganizationMember, User

router = APIRouter()


# ── Helpers ──────────────────────────────────


async def _get_company_org(company_user: User, db: AsyncSession) -> Organization:
    """유저의 소속 조직을 반환. ADMIN/COMPANY/USER 모두 허용."""
    if company_user.role not in ("COMPANY", "ADMIN", "USER"):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    member = await db.scalar(
        select(OrganizationMember).where(OrganizationMember.user_id == company_user.id)
    )
    if not member:
        raise HTTPException(status_code=404, detail="소속 조직을 찾을 수 없습니다.")
    org = await db.scalar(select(Organization).where(Organization.id == member.organization_id))
    if not org:
        raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다.")
    return org


# ── Schemas ──────────────────────────────────


class PendingMember(BaseModel):
    member_id: str
    user_id: str
    user_name: str
    email: str
    created_at: datetime


class MemberRow(BaseModel):
    member_id: str
    user_id: str
    user_name: str
    email: str
    status: str
    joined_at: datetime | None
    created_at: datetime


class SimulationRow(BaseModel):
    id: str
    ad_id: str
    status: str
    sample_size: int
    created_by_name: str | None
    created_at: datetime


class GenerationRow(BaseModel):
    id: str
    status: str
    product_name: str | None
    project_name: str | None
    created_by_name: str | None
    created_at: datetime


# ── Endpoints ────────────────────────────────


@router.get("/pending-members", response_model=list[PendingMember])
async def list_pending_members(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """승인 대기 중인 USER 목록."""
    org = await _get_company_org(current_user, db)

    rows = await db.execute(
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.status == "PENDING",
            User.role == "USER",
        )
    )
    return [
        PendingMember(
            member_id=str(m.id),
            user_id=str(u.id),
            user_name=u.name,
            email=u.email,
            created_at=m.created_at,
        )
        for m, u in rows.all()
    ]


@router.post("/approve-member/{member_id}")
async def approve_member(
    member_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """USER 멤버 승인 — org_member.status + user.status → ACTIVE."""
    org = await _get_company_org(current_user, db)

    member = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == org.id,
        )
    )
    if not member:
        raise HTTPException(status_code=404, detail="멤버를 찾을 수 없습니다.")

    user = await db.scalar(select(User).where(User.id == member.user_id))
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")

    member.status = "ACTIVE"
    member.joined_at = datetime.utcnow()
    user.status = "ACTIVE"
    return {"ok": True}


@router.post("/reject-member/{member_id}")
async def reject_member(
    member_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """USER 멤버 반려."""
    org = await _get_company_org(current_user, db)

    member = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == org.id,
        )
    )
    if not member:
        raise HTTPException(status_code=404, detail="멤버를 찾을 수 없습니다.")

    user = await db.scalar(select(User).where(User.id == member.user_id))
    if user:
        user.status = "REJECTED"
    member.status = "REJECTED"
    return {"ok": True}


@router.get("/members", response_model=list[MemberRow])
async def list_members(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """소속 전체 멤버 목록."""
    org = await _get_company_org(current_user, db)

    rows = await db.execute(
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == org.id, User.role == "USER")
        .order_by(OrganizationMember.created_at.desc())
    )
    return [
        MemberRow(
            member_id=str(m.id),
            user_id=str(u.id),
            user_name=u.name,
            email=u.email,
            status=m.status,
            joined_at=m.joined_at,
            created_at=m.created_at,
        )
        for m, u in rows.all()
    ]


@router.get("/simulations", response_model=list[SimulationRow])
async def list_company_simulations(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """소속 조직의 시뮬레이션 내역."""
    org = await _get_company_org(current_user, db)

    result = await db.execute(
        text("""
            SELECT s.id, s.ad_id, s.status, s.sample_size, s.created_at, u.name AS created_by_name
            FROM simulations s
            LEFT JOIN users u ON u.id = s.created_by
            WHERE s.organization_id = :org_id
            ORDER BY s.created_at DESC
            LIMIT :limit
        """),
        {"org_id": org.id, "limit": limit},
    )
    return [
        SimulationRow(
            id=str(r.id),
            ad_id=str(r.ad_id),
            status=r.status,
            sample_size=r.sample_size,
            created_by_name=r.created_by_name,
            created_at=r.created_at,
        )
        for r in result
    ]


@router.get("/generations", response_model=list[GenerationRow])
async def list_company_generations(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """소속 조직의 제너레이터 내역."""
    org = await _get_company_org(current_user, db)

    result = await db.execute(
        text("""
            SELECT g.id, g.status, g.input, g.created_at,
                   p.name AS project_name,
                   u.name AS created_by_name
            FROM ad_generations g
            JOIN projects p ON p.id = g.project_id
            LEFT JOIN users u ON u.id = g.created_by
            WHERE p.organization_id = :org_id
            ORDER BY g.created_at DESC
            LIMIT :limit
        """),
        {"org_id": org.id, "limit": limit},
    )
    return [
        GenerationRow(
            id=str(r.id),
            status=r.status,
            product_name=(r.input or {}).get("product_name") if r.input else None,
            project_name=r.project_name,
            created_by_name=r.created_by_name,
            created_at=r.created_at,
        )
        for r in result
    ]
