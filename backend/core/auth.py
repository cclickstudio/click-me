"""JWT 유틸 + 비밀번호 해싱 (Cognito 전환 전 임시 구현)."""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import get_db
from core.models import OrganizationMember, User

bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="인증 토큰이 없습니다."
        )
    try:
        payload = decode_token(creds.credentials)
        user_id: str = payload["sub"]
    except JWTError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다."
        ) from err

    user = await db.scalar(select(User).where(User.id == user_id))
    if not user or user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="유저를 찾을 수 없습니다."
        )
    return user


async def optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """토큰 있으면 검증된 ACTIVE 유저, 없거나 무효면 None (401 안 냄) — 선택적 인증용.

    mock/데모는 무인증 허용, live는 org 스코프 — 둘을 한 엔드포인트에서 가르는 공용 의존성.
    """
    if not creds:
        return None
    try:
        user_id: str = decode_token(creds.credentials)["sub"]
    except (JWTError, KeyError):
        return None
    user = await db.scalar(select(User).where(User.id == user_id))
    return user if user and user.status == "ACTIVE" else None


async def user_org_id(user: User, db: AsyncSession) -> uuid.UUID | None:
    """로그인 유저의 소속 org id (없으면 None) — raise 없이 조회만(호출자가 404/409 결정)."""
    return await db.scalar(
        select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user.id)
    )


async def require_user_org(user: User, db: AsyncSession) -> uuid.UUID:
    """로그인 유저의 소속 org — 없으면 409. 라우터별 복붙 대신 이 공용 함수를 쓴다."""
    org_id = await user_org_id(user, db)
    if org_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="소속 조직이 없습니다.")
    return org_id


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한이 필요합니다."
        )
    return user
