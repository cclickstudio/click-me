"""관리자 전용 API — ADMIN 역할만 접근 가능."""

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import hash_password, require_admin
from core.db import get_db
from core.models import Organization, OrganizationMember, User

router = APIRouter()


def _slugify(name: str) -> str:
    """조직 이름을 URL-safe slug로 변환 + 충돌 방지용 랜덤 접미사."""
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug[:80] + "-" + uuid.uuid4().hex[:6]


# ── Schemas ──────────────────────────────────


class PendingCompany(BaseModel):
    user_id: str
    user_name: str
    login_id: str
    company_name: str
    organization_id: str
    created_at: datetime


class UserRow(BaseModel):
    id: str
    login_id: str
    name: str
    role: str
    status: str
    created_at: datetime
    organization_name: str | None = None  # 소속 조직명(멤버십 기준, ADMIN 등 미소속이면 None)


class SimulationRow(BaseModel):
    id: str
    ad_title: str | None
    status: str
    sample_size: int
    created_by_name: str | None
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
                login_id=user.login_id,
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


@router.delete("/companies/{org_id}")
async def delete_company(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """회사(조직) 하드 삭제 — 하위 프로젝트·시뮬·생성·멤버·유저 계정까지 전부 제거."""
    # 하드 삭제 헬퍼 재사용 (시뮬·광고·생성 cascade)
    from api.routers.projects import _purge_ads, _purge_generations, _purge_simulations

    org = await db.scalar(select(Organization).where(Organization.id == org_id))
    if not org:
        raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다.")

    p = {"org": org_id}
    proj_sub = "SELECT id FROM projects WHERE organization_id = :org"

    # 1. 조직의 모든 시뮬레이션(직접 소속 또는 프로젝트 광고 경유)과 자식
    await _purge_simulations(
        db,
        "SELECT id FROM simulations WHERE organization_id = :org "
        f"OR ad_id IN (SELECT id FROM ads WHERE project_id IN ({proj_sub}))",
        p,
    )
    await db.execute(
        text(f"DELETE FROM simulation_comparisons WHERE project_id IN ({proj_sub})"), p
    )
    # 2. 프로젝트 하위 광고·생성·채팅
    await _purge_ads(db, f"SELECT id FROM ads WHERE project_id IN ({proj_sub})", p)
    await _purge_generations(
        db, f"SELECT id FROM ad_generations WHERE project_id IN ({proj_sub})", p
    )
    await db.execute(text(f"DELETE FROM chat_sessions WHERE project_id IN ({proj_sub})"), p)
    await db.execute(text("DELETE FROM projects WHERE organization_id = :org"), p)
    # 3. 구독·멤버·유저 계정
    await db.execute(text("DELETE FROM organization_subscriptions WHERE organization_id = :org"), p)
    member_users = (
        (
            await db.execute(
                text("SELECT user_id FROM organization_members WHERE organization_id = :org"), p
            )
        )
        .scalars()
        .all()
    )
    await db.execute(text("DELETE FROM organization_members WHERE organization_id = :org"), p)
    for uid in member_users:
        await db.execute(
            text("UPDATE users SET created_by = NULL WHERE created_by = :uid"), {"uid": uid}
        )
        await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
    # 4. 조직
    await db.execute(text("DELETE FROM organizations WHERE id = :org"), p)
    await db.commit()
    return {"ok": True}


# ── 전체 조직 목록 ────────────────────────────


class OrganizationRow(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime


@router.get("/organizations", response_model=list[OrganizationRow])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """전체 조직 목록 — 프로젝트가 0개인 회사도 포함."""
    rows = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    return [
        OrganizationRow(
            id=str(o.id),
            name=o.name,
            status=o.status,
            created_at=o.created_at,
        )
        for o in rows.scalars()
    ]


# ── 전체 유저 목록 ────────────────────────────


@router.get("/users", response_model=list[UserRow])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    # 소속 조직명은 멤버십(OrganizationMember)으로만 알 수 있어 outerjoin — 미소속(ADMIN 등)은 None.
    rows = await db.execute(
        select(User, Organization.name)
        .outerjoin(OrganizationMember, OrganizationMember.user_id == User.id)
        .outerjoin(Organization, Organization.id == OrganizationMember.organization_id)
        .order_by(User.created_at.desc())
    )
    return [
        UserRow(
            id=str(u.id),
            login_id=u.login_id,
            name=u.name,
            role=u.role,
            status=u.status,
            created_at=u.created_at,
            organization_name=org_name,
        )
        for u, org_name in rows.all()
    ]


class AdminCreateUser(BaseModel):
    name: str
    login_id: str
    password: str
    role: str  # ADMIN | COMPANY | USER
    company_name: str | None = None  # role=COMPANY — 새로 만들 조직 이름
    organization_id: str | None = None  # role=USER — 소속시킬 기존 조직


@router.post("/users", response_model=UserRow, status_code=201)
async def create_user(
    body: AdminCreateUser,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """ADMIN이 계정을 직접 생성. role에 따라 조직 생성(COMPANY)·조직 소속(USER) 처리.

    - ADMIN: 조직 없이 단독 계정.
    - COMPANY: company_name으로 새 조직(ACTIVE) 생성 + OWNER 멤버 등록.
    - USER: organization_id의 기존 조직에 MEMBER로 소속.
    모두 ACTIVE 상태로 생성(승인 절차 없이 바로 사용 가능).
    """
    role = body.role.upper()
    if role not in ("ADMIN", "COMPANY", "USER"):
        raise HTTPException(status_code=400, detail="역할은 ADMIN/COMPANY/USER 중 하나여야 합니다.")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다.")
    if await db.scalar(select(User).where(User.login_id == body.login_id)):
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")

    user = User(
        login_id=body.login_id,
        password_hash=hash_password(body.password),
        name=body.name,
        role=role,
        status="ACTIVE",
        # COMPANY/USER는 발급된 임시 비번 → 최초 로그인 시 변경 유도
        must_change_password=role in ("COMPANY", "USER"),
    )
    db.add(user)
    await db.flush()

    if role == "COMPANY":
        if not body.company_name:
            raise HTTPException(status_code=400, detail="회사명을 입력해주세요.")
        org = Organization(
            name=body.company_name,
            slug=_slugify(body.company_name),
            status="ACTIVE",
        )
        db.add(org)
        await db.flush()
        db.add(
            OrganizationMember(
                organization_id=org.id,
                user_id=user.id,
                role="OWNER",
                status="ACTIVE",
                joined_at=datetime.utcnow(),
            )
        )
    elif role == "USER":
        if not body.organization_id:
            raise HTTPException(status_code=400, detail="소속 조직을 선택해주세요.")
        org = await db.scalar(select(Organization).where(Organization.id == body.organization_id))
        if not org:
            raise HTTPException(status_code=404, detail="존재하지 않는 조직입니다.")
        db.add(
            OrganizationMember(
                organization_id=org.id,
                user_id=user.id,
                role="MEMBER",
                status="ACTIVE",
                joined_at=datetime.utcnow(),
            )
        )

    await db.flush()
    await db.refresh(user)
    return UserRow(
        id=str(user.id),
        login_id=user.login_id,
        name=user.name,
        role=user.role,
        status=user.status,
        created_at=user.created_at,
    )


class AdminUpdateUser(BaseModel):
    name: str | None = None
    password: str | None = None  # 값이 있으면 비밀번호 재설정


@router.patch("/users/{user_id}", response_model=UserRow)
async def update_user(
    user_id: str,
    body: AdminUpdateUser,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """계정 이름·비밀번호 수정. (역할·조직은 변경하지 않음)"""
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")

    if body.name is not None and body.name.strip():
        user.name = body.name.strip()
    if body.password:
        if len(body.password) < 8:
            raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다.")
        user.password_hash = hash_password(body.password)

    await db.flush()
    await db.refresh(user)
    return UserRow(
        id=str(user.id),
        login_id=user.login_id,
        name=user.name,
        role=user.role,
        status=user.status,
        created_at=user.created_at,
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    """계정 삭제. COMPANY는 조직째 삭제(delete-company)를 쓰도록 막고, 그 외 계정만 처리.

    삭제 대상이 만든 콘텐츠의 created_by는 실행 ADMIN에게 이전한다(FK NOT NULL).
    """
    if user_id == str(current_admin.id):
        raise HTTPException(status_code=400, detail="본인 계정은 삭제할 수 없습니다.")

    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
    if user.role == "COMPANY":
        raise HTTPException(
            status_code=400,
            detail="COMPANY 계정은 '조직 삭제'로 회사째 삭제해주세요.",
        )

    p = {"uid": user_id, "actor": str(current_admin.id)}
    for table in ("projects", "simulations", "ads", "ad_generations"):
        await db.execute(text(f"UPDATE {table} SET created_by = :actor WHERE created_by = :uid"), p)
    await db.execute(
        text("UPDATE organization_members SET invited_by = NULL WHERE invited_by = :uid"),
        {"uid": user_id},
    )
    await db.execute(
        text("UPDATE users SET created_by = NULL WHERE created_by = :uid"), {"uid": user_id}
    )
    await db.execute(
        text("DELETE FROM organization_members WHERE user_id = :uid"), {"uid": user_id}
    )
    await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
    return {"ok": True}


# ── 전체 시뮬레이션 내역 ──────────────────────


@router.get("/simulations", response_model=list[SimulationRow])
async def list_simulations(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = await db.execute(
        text("""
            SELECT s.id, s.status, s.sample_size, s.created_at,
                   a.title AS ad_title,
                   u.name  AS created_by_name
            FROM simulations s
            LEFT JOIN ads   a ON a.id = s.ad_id
            LEFT JOIN users u ON u.id = s.created_by
            ORDER BY s.created_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    )
    return [
        SimulationRow(
            id=str(r.id),
            ad_title=r.ad_title,
            status=r.status,
            sample_size=r.sample_size,
            created_by_name=r.created_by_name,
            created_at=r.created_at,
        )
        for r in rows.mappings()
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
    from sqlalchemy import func

    from core.models import ChatMessage, ChatSession

    # 정규화 후 메시지 수는 chat_messages 카운트로 — 세션별 LEFT JOIN 집계.
    rows = await db.execute(
        select(ChatSession, func.count(ChatMessage.id))
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .group_by(ChatSession.id)
        # 최근 활동(메시지 추가 시 갱신되는 updated_at) 순 — 생성일순이면 오래전 만든
        # 세션을 오늘 써도 목록 위로 안 올라와 "최근 채팅이 안 보인다"는 문제가 생긴다.
        .order_by(ChatSession.updated_at.desc())
        .limit(limit)
    )
    return [
        ChatRow(
            id=str(s.id),
            project_id=str(s.project_id) if s.project_id else None,
            message_count=count,
            created_at=s.created_at,
        )
        for s, count in rows.all()
    ]
