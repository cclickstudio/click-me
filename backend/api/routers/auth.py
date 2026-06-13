"""회원가입 / 로그인 / 내 정보 API."""

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import create_access_token, get_current_user, hash_password, verify_password
from core.db import get_db
from core.models import Organization, OrganizationMember, User

router = APIRouter()


# ── Schemas ──────────────────────────────────


class CompanySignUpRequest(BaseModel):
    name: str  # 담당자 이름
    email: EmailStr
    password: str
    company_name: str  # 조직 이름


class UserSignUpRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    organization_id: uuid.UUID  # 소속 회사 ID


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    status: str
    organization_id: str | None = None  # USER/COMPANY의 소속 조직 ID

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── Helpers ──────────────────────────────────


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug[:80] + "-" + uuid.uuid4().hex[:6]


async def _get_org_id_for_user(user: User, db: AsyncSession) -> str | None:
    """USER/COMPANY의 소속 organizations.id를 반환."""
    member = await db.scalar(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    )
    return str(member.organization_id) if member else None


# ── Endpoints ────────────────────────────────


@router.post("/signup/company", response_model=AuthResponse, status_code=201)
async def signup_company(body: CompanySignUpRequest, db: AsyncSession = Depends(get_db)):
    """기업 회원가입 — COMPANY 역할, ADMIN 승인 대기."""
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다.")

    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")

    # 유저 생성 (PENDING — ADMIN 승인 필요)
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
        role="COMPANY",
        status="PENDING",
    )
    db.add(user)
    await db.flush()

    # 조직 생성 (PENDING)
    org = Organization(
        name=body.company_name,
        slug=_slugify(body.company_name),
        status="PENDING",
    )
    db.add(org)
    await db.flush()

    # 담당자를 조직 OWNER 멤버로 등록 (바로 ACTIVE — 조직 내 권한)
    member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role="OWNER",
        status="ACTIVE",
        joined_at=datetime.utcnow(),
    )
    db.add(member)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(str(user.id), user.role)
    user_out = UserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        status=user.status,
        organization_id=str(org.id),
    )
    return AuthResponse(access_token=token, user=user_out)


@router.post("/signup/user", response_model=AuthResponse, status_code=201)
async def signup_user(body: UserSignUpRequest, db: AsyncSession = Depends(get_db)):
    """개인(직원) 회원가입 — USER 역할, COMPANY 승인 대기."""
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다.")

    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")

    # 조직 존재 + ACTIVE 여부 확인
    org = await db.scalar(select(Organization).where(Organization.id == body.organization_id))
    if not org:
        raise HTTPException(status_code=404, detail="존재하지 않는 조직 ID입니다.")
    if org.status != "ACTIVE":
        raise HTTPException(status_code=400, detail="아직 승인되지 않은 회사입니다.")

    # 유저 생성 (PENDING — COMPANY 승인 필요)
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
        role="USER",
        status="PENDING",
    )
    db.add(user)
    await db.flush()

    # 조직 멤버 등록 (PENDING)
    member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role="MEMBER",
        status="PENDING",
    )
    db.add(member)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(str(user.id), user.role)
    user_out = UserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        status=user.status,
        organization_id=str(org.id),
    )
    return AuthResponse(access_token=token, user=user_out)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    user.last_login_at = datetime.utcnow()
    org_id = await _get_org_id_for_user(user, db)

    token = create_access_token(str(user.id), user.role)
    user_out = UserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        status=user.status,
        organization_id=org_id,
    )
    return AuthResponse(access_token=token, user=user_out)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org_id = await _get_org_id_for_user(user, db)
    return UserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        status=user.status,
        organization_id=org_id,
    )
