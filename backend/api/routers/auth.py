"""내 정보 API. (회원가입·자체 로그인 없음 — 계정은 ADMIN·COMPANY가 직접 생성, 인증은 Cognito)"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core import cognito_admin
from core.auth import get_current_user
from core.db import get_db
from core.models import OrganizationMember, User

router = APIRouter()


# ── Schemas ──────────────────────────────────


class UserOut(BaseModel):
    id: str
    login_id: str
    name: str
    role: str
    status: str
    must_change_password: bool = False
    phone_num: str | None = None
    user_email: str | None = None
    team_id: str | None = None  # 소속 팀(USER)
    organization_id: str | None = None  # USER/COMPANY의 소속 조직 ID

    model_config = {"from_attributes": True}


class ChangePasswordRequest(BaseModel):
    new_password: str


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    phone_num: str | None = None
    user_email: str | None = None


# ── Helpers ──────────────────────────────────


async def _get_org_id_for_user(user: User, db: AsyncSession) -> str | None:
    """USER/COMPANY의 소속 organizations.id를 반환."""
    member = await db.scalar(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    )
    return str(member.organization_id) if member else None


# ── Endpoints ────────────────────────────────


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org_id = await _get_org_id_for_user(user, db)
    return UserOut(
        id=str(user.id),
        login_id=user.login_id,
        name=user.name,
        role=user.role,
        status=user.status,
        must_change_password=user.must_change_password,
        phone_num=user.phone_num,
        user_email=user.user_email,
        team_id=str(user.team_id) if user.team_id else None,
        organization_id=org_id,
    )


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """본인 정보 수정 — 이름·전화번호·연락 이메일. (빈 문자열은 NULL 처리)"""
    if body.name is not None and body.name.strip():
        user.name = body.name.strip()
    if body.phone_num is not None:
        user.phone_num = body.phone_num.strip() or None
    if body.user_email is not None:
        user.user_email = body.user_email.strip() or None

    org_id = await _get_org_id_for_user(user, db)
    return UserOut(
        id=str(user.id),
        login_id=user.login_id,
        name=user.name,
        role=user.role,
        status=user.status,
        must_change_password=user.must_change_password,
        phone_num=user.phone_num,
        user_email=user.user_email,
        team_id=str(user.team_id) if user.team_id else None,
        organization_id=org_id,
    )


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """본인 비밀번호 변경 — 변경 후 must_change_password 해제."""
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다.")
    # cognito 모드면 Cognito 비번을 바꾸고 DB엔 placeholder. 실패 시 502(롤백).
    await cognito_admin.set_password(user.login_id, body.new_password)
    user.must_change_password = False
    return {"ok": True}
