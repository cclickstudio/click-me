"""인증 — JWT 발급/검증.

auth_provider 설정으로 두 모드를 병행 지원(점진 도입):
- "local"(기본): 자체 HS256 JWT(create_access_token 발급 + HS256 decode).
- "cognito": AWS Cognito User Pool의 **access token**을 JWKS(RS256)+issuer 로 검증.
  access token은 aud 클레임이 없고 client_id 를 가지므로 audience 대신 client_id 를 확인한다.
  username 클레임(= 우리 login_id)으로 DB User를 조회하고, role 은 cognito:groups 로 판별한다.

토큰은 Authorization: Bearer 헤더 우선, 없으면 access_token 쿠키에서 읽는다(SSE/EventSource는
헤더를 못 붙이므로 쿠키 폴백이 필요). 쿠키명은 ACCESS_COOKIE_NAME.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import get_db
from core.models import OrganizationMember, User

bearer = HTTPBearer(auto_error=False)

# 프론트가 access/refresh 토큰을 저장하는 쿠키명(프론트 authApi 와 규약 일치).
ACCESS_COOKIE_NAME = "access_token"

# role ↔ Cognito 그룹 매핑. 한 유저가 여러 그룹이면 이 우선순위로 택1(권한 높은 쪽).
_ROLE_PRIORITY = ("ADMIN", "COMPANY", "USER")

# Cognito JWKS 캐시 — 공개키는 거의 안 바뀌므로 프로세스 수명 동안 캐시.
# 검증 실패 시 1회 강제 갱신(키 회전 대비).
_jwks_cache: dict | None = None


def create_access_token(user_id: str, role: str) -> str:
    """local 모드 전용 — 자체 HS256 토큰 발급. cognito 모드에선 Cognito가 발급한다."""
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _fetch_jwks(force: bool = False) -> dict:
    global _jwks_cache
    if _jwks_cache is None or force:
        resp = httpx.get(settings.cognito_jwks_uri, timeout=5.0)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache


def _decode_cognito_token(token: str) -> dict:
    """Cognito access token을 JWKS(RS256)+issuer로 검증 후 claim 반환.

    access token은 aud 클레임이 없으므로 audience 검증을 끄고(client_id 클레임으로 대체 확인),
    token_use == "access" 를 요구한다.
    """
    last_err: JWTError | None = None
    for force in (False, True):  # 1차 실패 시 키 회전 가능성 → JWKS 강제 갱신 후 1회 재시도
        try:
            jwks = _fetch_jwks(force=force)
        except httpx.HTTPError as err:
            raise JWTError("Cognito JWKS 조회 실패") from err
        try:
            claims = jwt.decode(
                token,
                jwks,
                algorithms=["RS256"],
                issuer=settings.cognito_issuer,
                options={"verify_aud": False},  # access token엔 aud 없음 → client_id로 확인
            )
        except JWTError as err:
            last_err = err
            continue
        if claims.get("token_use") != "access":
            raise JWTError("access 토큰이 아닙니다(token_use != access).")
        if claims.get("client_id") != settings.cognito_app_client_id:
            raise JWTError("client_id 불일치.")
        return claims
    raise last_err or JWTError("토큰 검증 실패")


def _role_from_claims(payload: dict) -> str | None:
    """access token의 cognito:groups 에서 우리 role(ADMIN/COMPANY/USER)을 판별. 없으면 None."""
    groups = payload.get("cognito:groups") or []
    for role in _ROLE_PRIORITY:
        if role in groups:
            return role
    return None


def decode_token(token: str) -> dict:
    if settings.auth_provider == "cognito":
        return _decode_cognito_token(token)
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


async def _resolve_user(payload: dict, db: AsyncSession) -> User | None:
    """검증된 토큰 claim으로 DB User를 조회. cognito=login_id(username), local=user.id(sub)."""
    if settings.auth_provider == "cognito":
        # access token은 username, id token은 cognito:username. 둘 다 우리 login_id.
        username = payload.get("cognito:username") or payload.get("username")
        if not username:
            return None
        return await db.scalar(select(User).where(User.login_id == username))
    user_id = payload.get("sub")
    if not user_id:
        return None
    return await db.scalar(select(User).where(User.id == user_id))


def _extract_token(creds: HTTPAuthorizationCredentials | None, request: Request) -> str | None:
    """Authorization: Bearer 헤더 우선, 없으면 access_token 쿠키(SSE/EventSource 대응)."""
    if creds:
        return creds.credentials
    return request.cookies.get(ACCESS_COOKIE_NAME)


def _apply_token_role(user: User, payload: dict) -> None:
    """cognito 모드면 토큰의 그룹으로 role을 확정한다(토큰이 권위, DB는 동기화 폴백).

    DB role과 다르면 self-heal(같으면 no-op). local 모드는 DB role 유지.
    """
    if settings.auth_provider != "cognito":
        return
    role = _role_from_claims(payload)
    if role and user.role != role:
        user.role = role


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = _extract_token(creds, request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="인증 토큰이 없습니다."
        )
    try:
        payload = decode_token(token)
    except JWTError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다."
        ) from err

    user = await _resolve_user(payload, db)
    if not user or user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="유저를 찾을 수 없습니다."
        )
    _apply_token_role(user, payload)
    return user


async def get_current_user_optional(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """토큰이 있으면 유저, 없거나 무효면 None(401 미발생). 점진 도입 중 채팅 등에 사용."""
    token = _extract_token(creds, request)
    if not token:
        return None
    try:
        payload = decode_token(token)
    except JWTError:
        return None
    user = await _resolve_user(payload, db)
    if not user or user.status != "ACTIVE":
        return None
    _apply_token_role(user, payload)
    return user


# 선택적 인증 별칭 — 라우터는 optional_user 이름으로 사용(get_current_user_optional과 동일).
optional_user = get_current_user_optional


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
