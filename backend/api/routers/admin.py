"""관리자 전용 API — ADMIN 역할만 접근 가능."""

import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, case, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.projects import _purge_project
from core import cognito_admin
from core.auth import require_admin
from core.db import get_db
from core.models import Inquiry, Organization, OrganizationMember, User

router = APIRouter()


def _slugify(name: str) -> str:
    """조직 이름을 URL-safe slug로 변환 + 충돌 방지용 랜덤 접미사."""
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug[:80] + "-" + uuid.uuid4().hex[:6]


# ── Schemas ──────────────────────────────────


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
    created_by_role: str | None = None  # 실행자 역할(ADMIN|COMPANY|USER) — 내역서 '관리자' 표기용
    project_id: str | None = None  # 소속 프로젝트 id(내역 클릭→패널 열기용)
    project_name: str | None = None  # 소속 프로젝트명(내역 컬럼)
    org_name: str | None = None  # 소속 조직명(내역 org 컬럼·필터용)
    org_status: str | None = None  # 소속 조직 상태(ACTIVE|INACTIVE) — 삭제된 조직 표시·필터용
    created_at: datetime


class GenerationRow(BaseModel):
    id: str
    status: str
    product_name: str | None
    created_by_name: str | None
    created_by_role: str | None = None  # 실행자 역할(ADMIN|COMPANY|USER) — 내역서 '관리자' 표기용
    project_id: str | None = None  # 소속 프로젝트 id(내역 클릭→패널 열기용)
    project_name: str | None = None  # 소속 프로젝트명(내역 컬럼)
    org_name: str | None = None  # 소속 조직명(내역 org 컬럼·필터용)
    org_status: str | None = None  # 소속 조직 상태(ACTIVE|INACTIVE) — 삭제된 조직 표시·필터용
    created_at: datetime


class ChatRow(BaseModel):
    id: str
    project_id: str | None
    title: str | None = None  # 세션 제목(검색·표시용)
    message_count: int
    created_by_name: str | None = None  # 세션 개시자(실행자) — 0007 마이그레이션 이후 기록
    created_by_role: str | None = None  # 실행자 역할(ADMIN|COMPANY|USER) — 내역서 '관리자' 표기용
    project_name: str | None = None  # 소속 프로젝트명(내역 컬럼)
    org_name: str | None = None  # 소속 조직명(내역 org 컬럼·필터용)
    org_status: str | None = None  # 소속 조직 상태(ACTIVE|INACTIVE) — 삭제된 조직 표시·필터용
    created_at: datetime


# ── 회사(조직) 삭제 ───────────────────────────


@router.delete("/companies/{org_id}")
async def delete_company(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """회사(조직) 소프트 삭제 — 조직·소속 유저를 INACTIVE로 비활성화하고 Cognito 계정만 제거.

    프로젝트·시뮬·생성·채팅 데이터는 그대로 보존해, 관리자(개발진)가 삭제된 조직의 활동을
    사후 조회할 수 있게 한다. 유저는 status=INACTIVE로 인증이 차단되고(core/auth), Cognito에서는
    실제 삭제돼 로그인이 불가능해진다. (하드 삭제는 FK 참조로 실패하고 이력 추적도 불가능해 전환.)
    """
    org = await db.scalar(select(Organization).where(Organization.id == org_id))
    if not org:
        raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다.")

    # 소속 유저를 INACTIVE로 전환 + Cognito disable용 login_id 수집
    login_ids = await _org_member_login_ids(db, org_id, set_status="INACTIVE")
    org.status = "INACTIVE"
    await db.commit()

    # cognito 모드면 소속 유저를 Cognito에서 disable(로그인 차단, 복원 가능). best-effort.
    for lid in login_ids:
        await cognito_admin.disable_user(lid)
    return {"ok": True}


async def _org_member_login_ids(
    db: AsyncSession, org_id: str, set_status: str | None = None
) -> list[str]:
    """조직 소속 유저의 login_id를 수집. set_status가 있으면 각 유저 status도 함께 갱신."""
    member_ids = (
        (
            await db.execute(
                text("SELECT user_id FROM organization_members WHERE organization_id = :org"),
                {"org": org_id},
            )
        )
        .scalars()
        .all()
    )
    login_ids: list[str] = []
    if member_ids:
        users = (await db.scalars(select(User).where(User.id.in_(member_ids)))).all()
        for u in users:
            if set_status is not None:
                u.status = set_status
            login_ids.append(u.login_id)
    return login_ids


@router.post("/companies/{org_id}/restore")
async def restore_company(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """소프트 삭제한 회사(조직)를 복원 — 조직·소속 유저를 ACTIVE로 되돌리고 Cognito도 enable.

    Cognito 계정이 (과거 삭제 기반 흐름으로) 사라졌으면 enable_user가 role 그룹으로 재생성한다.
    """
    org = await db.scalar(select(Organization).where(Organization.id == org_id))
    if not org:
        raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다.")

    member_ids = (
        (
            await db.execute(
                text("SELECT user_id FROM organization_members WHERE organization_id = :org"),
                {"org": org_id},
            )
        )
        .scalars()
        .all()
    )
    restore: list[tuple[str, str]] = []
    if member_ids:
        users = (await db.scalars(select(User).where(User.id.in_(member_ids)))).all()
        for u in users:
            u.status = "ACTIVE"
            restore.append((u.login_id, u.role))
    org.status = "ACTIVE"
    await db.commit()

    for lid, role in restore:
        await cognito_admin.enable_user(lid, role)
    return {"ok": True}


@router.delete("/companies/{org_id}/purge")
async def purge_company(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """회사(조직) 영구 삭제 — Cognito + DB(조직·멤버·유저) + 하위 프로젝트/시뮬/제너/채팅 하드 삭제.

    복구 불가. 소프트 삭제(INACTIVE)와 달리 사후 조회용 데이터도 전부 제거한다.
    """
    org = await db.scalar(select(Organization).where(Organization.id == org_id))
    if not org:
        raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다.")

    member_ids = (
        (
            await db.execute(
                text("SELECT user_id FROM organization_members WHERE organization_id = :org"),
                {"org": org_id},
            )
        )
        .scalars()
        .all()
    )
    login_ids = (
        [u.login_id for u in (await db.scalars(select(User).where(User.id.in_(member_ids)))).all()]
        if member_ids
        else []
    )

    # 하위 프로젝트를 자식(광고·시뮬·제너·채팅)까지 하드 삭제(projects.py 헬퍼 재사용).
    proj_ids = (
        (
            await db.execute(
                text("SELECT id FROM projects WHERE organization_id = :org"), {"org": org_id}
            )
        )
        .scalars()
        .all()
    )
    for pid in proj_ids:
        await _purge_project(db, str(pid))

    p = {"org": org_id}
    # org/유저를 참조하는 잔여 레코드 정리(NO ACTION FK가 삭제를 막지 않도록 먼저 제거).
    await db.execute(text("DELETE FROM brand_kits WHERE organization_id = :org"), p)
    await db.execute(
        text("DELETE FROM management_campaign_kpi_overrides WHERE organization_id = :org"), p
    )
    await db.execute(
        text("DELETE FROM management_meta_connections WHERE organization_id = :org"), p
    )
    await db.execute(text("DELETE FROM teams WHERE organization_id = :org"), p)
    await db.execute(text("DELETE FROM organization_members WHERE organization_id = :org"), p)
    if member_ids:
        # 멤버끼리의 created_by 자기참조는 단일 DELETE ANY로 함께 정리된다.
        await db.execute(
            text("UPDATE users SET created_by = NULL WHERE created_by = ANY(:ids)"),
            {"ids": member_ids},
        )
        await db.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": member_ids})
    await db.execute(text("DELETE FROM organizations WHERE id = :org"), p)
    await db.commit()

    for lid in login_ids:
        await cognito_admin.delete_user(lid)
    return {"ok": True}


# ── 전체 조직 목록 ────────────────────────────


class OrganizationRow(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime
    owner_login_id: str | None = None  # 오너(COMPANY 계정) 아이디 — 조직 관리 화면 표시용
    owner_name: str | None = None


_ORG_SORT_COLS = {
    "name": Organization.name,
    "created_at": Organization.created_at,
    "status": Organization.status,
}


@router.get("/organizations", response_model=list[OrganizationRow])
async def list_organizations(
    limit: int = 20,
    offset: int = 0,
    sort: str = "created_at",
    order: str = "desc",
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """전체 조직 목록 — 프로젝트가 0개인 회사도 포함. limit/offset·sort(name|created_at|status)."""
    limit, offset = _clamp_page(limit, offset)
    col = _ORG_SORT_COLS.get(sort, Organization.created_at)
    order_by = col.asc() if str(order).lower() == "asc" else col.desc()
    # 오너(OWNER 멤버십) 계정의 아이디·이름을 같이 내려준다 — 조직 관리 화면에 "담당 계정" 표시용.
    stmt = (
        select(Organization, User.login_id, User.name)
        .outerjoin(
            OrganizationMember,
            and_(
                OrganizationMember.organization_id == Organization.id,
                OrganizationMember.role == "OWNER",
            ),
        )
        .outerjoin(User, User.id == OrganizationMember.user_id)
        .order_by(order_by)
        .limit(limit)
        .offset(offset)
    )
    rows = await db.execute(stmt)
    return [
        OrganizationRow(
            id=str(o.id),
            name=o.name,
            status=o.status,
            created_at=o.created_at,
            owner_login_id=owner_login_id,
            owner_name=owner_name,
        )
        for o, owner_login_id, owner_name in rows.all()
    ]


# ── 전체 유저 목록 ────────────────────────────


_USER_SORT_COLS = {
    "name": User.name,
    "created_at": User.created_at,
    "status": User.status,
}
# 기본 정렬(sort 미지정 시) — ADMIN → COMPANY → USER 우선순위.
_USER_ROLE_PRIORITY = case((User.role == "ADMIN", 0), (User.role == "COMPANY", 1), else_=2)


@router.get("/users", response_model=list[UserRow])
async def list_users(
    limit: int = 20,
    offset: int = 0,
    sort: str = "role",
    order: str = "desc",
    role: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """전체 유저 목록. limit/offset·sort(role|name|created_at|status)·role 필터. 기본 ADMIN→USER.

    role은 콤마로 여러 값을 받는다(예: "ADMIN,USER") — 회원 관리 화면이 COMPANY를 제외하고
    조회할 때 사용.
    """
    limit, offset = _clamp_page(limit, offset)
    # 소속 조직명은 멤버십(OrganizationMember)으로만 알 수 있어 outerjoin — 미소속(ADMIN 등)은 None.
    stmt = (
        select(User, Organization.name)
        .outerjoin(OrganizationMember, OrganizationMember.user_id == User.id)
        .outerjoin(Organization, Organization.id == OrganizationMember.organization_id)
    )
    if role:
        roles = [r.strip().upper() for r in role.split(",") if r.strip()]
        if len(roles) > 1:
            stmt = stmt.where(User.role.in_(roles))
        else:
            stmt = stmt.where(User.role == roles[0])
    if sort in _USER_SORT_COLS:
        col = _USER_SORT_COLS[sort]
        stmt = stmt.order_by(col.asc() if str(order).lower() == "asc" else col.desc())
    else:
        # 기본: 역할 우선순위(ADMIN→USER) 후 최신순.
        stmt = stmt.order_by(_USER_ROLE_PRIORITY.asc(), User.created_at.desc())
    stmt = stmt.limit(limit).offset(offset)
    rows = await db.execute(stmt)
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
    # cognito 모드면 Cognito에도 동일 계정 생성(username=login_id). 실패 시 502 → DB 롤백.
    await cognito_admin.create_user(user.login_id, body.password, role)
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
        # cognito 모드면 Cognito 비번도 재설정. 실패 시 502 → DB 롤백(불일치 방지).
        await cognito_admin.set_password(user.login_id, body.password)

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
    """계정 소프트 삭제 — 유저를 INACTIVE로 비활성화하고 Cognito 계정만 제거.

    유저가 만든 콘텐츠(프로젝트·시뮬·생성·채팅)는 보존해 관리자가 사후 조회할 수 있게 한다.
    status=INACTIVE로 인증이 차단되고(core/auth), Cognito에서는 실제 삭제돼 로그인이 불가능해진다.
    COMPANY는 조직째 삭제(delete-company)를 쓰도록 막는다.
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

    user.status = "INACTIVE"
    await db.commit()
    # cognito 모드면 Cognito 사용자를 disable(로그인 차단, 복원 가능). best-effort.
    await cognito_admin.disable_user(user.login_id)
    return {"ok": True}


@router.post("/users/{user_id}/restore")
async def restore_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """소프트 삭제한 계정을 복원 — status=ACTIVE + Cognito enable(없으면 role 그룹으로 재생성)."""
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
    user.status = "ACTIVE"
    await db.commit()
    await cognito_admin.enable_user(user.login_id, user.role)
    return {"ok": True}


@router.delete("/users/{user_id}/purge")
async def purge_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    """계정 영구 삭제 — Cognito + DB(유저·멤버십) + 본인이 만든 프로젝트/시뮬/제너/채팅 하드 삭제.

    복구 불가. COMPANY는 '조직 영구삭제(purge-company)'로 회사째 지운다.
    """
    if user_id == str(current_admin.id):
        raise HTTPException(status_code=400, detail="본인 계정은 삭제할 수 없습니다.")

    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
    if user.role == "COMPANY":
        raise HTTPException(
            status_code=400,
            detail="COMPANY 계정은 '조직 영구삭제'로 회사째 삭제해주세요.",
        )
    login_id = user.login_id

    # 본인이 만든 프로젝트를 자식까지 하드 삭제(projects.py 헬퍼 재사용).
    proj_ids = (
        (await db.execute(text("SELECT id FROM projects WHERE created_by = :u"), {"u": user_id}))
        .scalars()
        .all()
    )
    for pid in proj_ids:
        await _purge_project(db, str(pid))

    u = {"u": user_id}
    # 유저를 참조하는 잔여 레코드 정리(NO ACTION FK가 삭제를 막지 않도록).
    await db.execute(text("UPDATE users SET created_by = NULL WHERE created_by = :u"), u)
    await db.execute(
        text("UPDATE organization_members SET invited_by = NULL WHERE invited_by = :u"), u
    )
    await db.execute(text("DELETE FROM management_campaign_kpi_overrides WHERE updated_by = :u"), u)
    await db.execute(text("DELETE FROM organization_members WHERE user_id = :u"), u)
    await db.execute(text("DELETE FROM users WHERE id = :u"), u)
    await db.commit()

    await cognito_admin.delete_user(login_id)
    return {"ok": True}


# ── 내역 목록 공용(페이지네이션·정렬·검색·org 필터) ────────────────
# admin 내역 3종(시뮬·제너·채팅)이 공유하는 목록 파라미터 처리. 정렬 컬럼은 화이트리스트로
# 고정해 ORDER BY 인젝션을 막는다. status 필터는 화면 버킷(completed/in_progress/failed)을
# 각 테이블의 실제 상태값으로 번역해 조건에 건다.

_HISTORY_LIMIT_MAX = 200


def _clamp_page(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(limit, _HISTORY_LIMIT_MAX)), max(0, offset)


def _order_clause(sort: str, order: str, cols: dict[str, str], default_col: str) -> str:
    """화이트리스트 정렬 절 — sort는 cols 키, order는 asc/desc만 허용(그 외 desc)."""
    col = cols.get(sort, default_col)
    direction = "ASC" if str(order).lower() == "asc" else "DESC"
    return f"{col} {direction} NULLS LAST"


def _org_filter_uuid(x_org_id: str | None) -> uuid.UUID | None:
    """admin이 선택한 X-Org-Id → UUID. 없거나 형식 오류면 None(전체)."""
    if not x_org_id:
        return None
    try:
        return uuid.UUID(x_org_id)
    except ValueError:
        return None


def _status_values(bucket: str | None, mapping: dict[str, tuple[str, ...]]) -> list[str] | None:
    """상태 버킷(completed/in_progress/failed)을 테이블 실제 상태값 리스트로 번역. 없으면 None."""
    if not bucket:
        return None
    vals = mapping.get(bucket)
    return list(vals) if vals else None


# ── 전체 시뮬레이션 내역 ──────────────────────

_SIM_SORT_COLS = {"created_at": "s.created_at", "title": "a.title", "org_name": "o.name"}
_SIM_STATUS = {
    "completed": ("COMPLETED",),
    "in_progress": ("QUEUED", "RUNNING"),
    "failed": ("FAILED",),
}


@router.get("/simulations", response_model=list[SimulationRow])
async def list_simulations(
    limit: int = 20,
    offset: int = 0,
    sort: str = "created_at",
    order: str = "desc",
    status: str | None = None,
    org_status: str | None = None,
    search_field: str = "title",
    search: str | None = None,
    x_org_id: str | None = Header(None, alias="X-Org-Id"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    limit, offset = _clamp_page(limit, offset)
    params: dict = {"limit": limit, "offset": offset}
    where = ["s.deleted_at IS NULL"]
    org = _org_filter_uuid(x_org_id)
    if org is not None:
        where.append("s.organization_id = :org_id")
        params["org_id"] = org
    statuses = _status_values(status, _SIM_STATUS)
    if statuses:
        where.append("s.status = ANY(:statuses)")
        params["statuses"] = statuses
    if org_status:
        where.append("o.status = :org_status")
        params["org_status"] = org_status
    if search:
        col = "o.name" if search_field == "org_name" else "a.title"
        where.append(f"{col} ILIKE :q")
        params["q"] = f"%{search}%"
    order_by = _order_clause(sort, order, _SIM_SORT_COLS, "s.created_at")
    rows = await db.execute(
        text(f"""
            SELECT s.id, s.status, s.sample_size, s.created_at,
                   a.title AS ad_title,
                   u.name  AS created_by_name,
                   u.role  AS created_by_role,
                   p.id    AS project_id,
                   p.name  AS project_name,
                   o.name  AS org_name,
                   o.status AS org_status
            FROM simulations s
            LEFT JOIN ads   a ON a.id = s.ad_id
            LEFT JOIN projects p ON p.id = a.project_id
            LEFT JOIN users u ON u.id = s.created_by
            LEFT JOIN organizations o ON o.id = s.organization_id
            WHERE {" AND ".join(where)}
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    return [
        SimulationRow(
            id=str(r.id),
            ad_title=r.ad_title,
            status=r.status,
            sample_size=r.sample_size,
            created_by_name=r.created_by_name,
            created_by_role=r.created_by_role,
            project_id=str(r.project_id) if r.project_id else None,
            project_name=r.project_name,
            org_name=r.org_name,
            org_status=r.org_status,
            created_at=r.created_at,
        )
        for r in rows.mappings()
    ]


# ── 전체 제너레이터 내역 ──────────────────────

_GEN_SORT_COLS = {
    "created_at": "g.created_at",
    "title": "g.input->>'product_name'",
    "org_name": "o.name",
}
_GEN_STATUS = {
    "completed": ("completed",),
    "in_progress": ("pending", "running"),
    "failed": ("failed",),
}


@router.get("/generations", response_model=list[GenerationRow])
async def list_generations(
    limit: int = 20,
    offset: int = 0,
    sort: str = "created_at",
    order: str = "desc",
    status: str | None = None,
    org_status: str | None = None,
    search_field: str = "title",
    search: str | None = None,
    x_org_id: str | None = Header(None, alias="X-Org-Id"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    limit, offset = _clamp_page(limit, offset)
    params: dict = {"limit": limit, "offset": offset}
    where = ["g.deleted_at IS NULL"]
    org = _org_filter_uuid(x_org_id)
    if org is not None:
        where.append("p.organization_id = :org_id")
        params["org_id"] = org
    statuses = _status_values(status, _GEN_STATUS)
    if statuses:
        where.append("g.status = ANY(:statuses)")
        params["statuses"] = statuses
    if org_status:
        where.append("o.status = :org_status")
        params["org_status"] = org_status
    if search:
        col = "o.name" if search_field == "org_name" else "g.input->>'product_name'"
        where.append(f"{col} ILIKE :q")
        params["q"] = f"%{search}%"
    order_by = _order_clause(sort, order, _GEN_SORT_COLS, "g.created_at")
    rows = await db.execute(
        text(f"""
            SELECT g.id, g.status, g.input, g.created_at,
                   u.name AS created_by_name,
                   u.role AS created_by_role,
                   p.id   AS project_id,
                   p.name AS project_name,
                   o.name AS org_name,
                   o.status AS org_status
            FROM ad_generations g
            LEFT JOIN projects p ON p.id = g.project_id
            LEFT JOIN organizations o ON o.id = p.organization_id
            LEFT JOIN users u ON u.id = g.created_by
            WHERE {" AND ".join(where)}
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    return [
        GenerationRow(
            id=str(r.id),
            status=r.status,
            product_name=(r.input or {}).get("product_name") if r.input else None,
            created_by_name=r.created_by_name,
            created_by_role=r.created_by_role,
            project_id=str(r.project_id) if r.project_id else None,
            project_name=r.project_name,
            org_name=r.org_name,
            org_status=r.org_status,
            created_at=r.created_at,
        )
        for r in rows.mappings()
    ]


# ── 전체 채팅 내역 ────────────────────────────

_CHAT_SORT_COLS = {"created_at": "cs.updated_at", "title": "cs.title", "org_name": "o.name"}


@router.get("/chats", response_model=list[ChatRow])
async def list_chats(
    limit: int = 20,
    offset: int = 0,
    sort: str = "created_at",
    order: str = "desc",
    org_status: str | None = None,
    search_field: str = "title",
    search: str | None = None,
    x_org_id: str | None = Header(None, alias="X-Org-Id"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    # 채팅은 상태 개념이 없어 status 필터를 받지 않는다. 최근 활동(updated_at) 기본 정렬.
    limit, offset = _clamp_page(limit, offset)
    params: dict = {"limit": limit, "offset": offset}
    where = ["1=1"]
    org = _org_filter_uuid(x_org_id)
    if org is not None:
        where.append("p.organization_id = :org_id")
        params["org_id"] = org
    if org_status:
        where.append("o.status = :org_status")
        params["org_status"] = org_status
    if search:
        col = "o.name" if search_field == "org_name" else "cs.title"
        where.append(f"{col} ILIKE :q")
        params["q"] = f"%{search}%"
    order_by = _order_clause(sort, order, _CHAT_SORT_COLS, "cs.updated_at")
    rows = await db.execute(
        text(f"""
            SELECT cs.id, cs.project_id, cs.title, cs.created_at,
                   u.name AS created_by_name,
                   u.role AS created_by_role,
                   p.name AS project_name,
                   o.name AS org_name,
                   o.status AS org_status,
                   COUNT(cm.id) AS message_count
            FROM chat_sessions cs
            LEFT JOIN chat_messages cm ON cm.session_id = cs.id
            LEFT JOIN projects p ON p.id = cs.project_id
            LEFT JOIN organizations o ON o.id = p.organization_id
            LEFT JOIN users u ON u.id = cs.created_by
            WHERE {" AND ".join(where)}
            GROUP BY cs.id, u.name, u.role, p.name, o.name, o.status
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    return [
        ChatRow(
            id=str(r.id),
            project_id=str(r.project_id) if r.project_id else None,
            title=r.title,
            message_count=r.message_count,
            created_by_name=r.created_by_name,
            created_by_role=r.created_by_role,
            project_name=r.project_name,
            org_name=r.org_name,
            org_status=r.org_status,
            created_at=r.created_at,
        )
        for r in rows.mappings()
    ]


# ── 고객 문의 (ADMIN 조회·해결) — append-only ──────────────────────────


class InquiryOut(BaseModel):
    id: str
    title: str
    content: str
    contact_email: str | None
    is_resolved: bool
    created_at: datetime
    resolved_at: datetime | None


@router.get("/inquiries")
async def list_inquiries(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """전체 문의 목록(최신순). 프론트가 상태 탭으로 필터."""
    rows = (await db.execute(select(Inquiry).order_by(Inquiry.created_at.desc()))).scalars().all()
    return {
        "inquiries": [
            InquiryOut(
                id=str(r.id),
                title=r.title,
                content=r.content,
                contact_email=r.contact_email,
                is_resolved=r.is_resolved,
                created_at=r.created_at,
                resolved_at=r.resolved_at,
            )
            for r in rows
        ]
    }


@router.patch("/inquiries/{inquiry_id}/resolve")
async def resolve_inquiry(
    inquiry_id: str,
    resolved: bool = True,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """문의 해결 상태 토글."""
    try:
        pk = uuid.UUID(inquiry_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.") from e
    row = await db.get(Inquiry, pk)
    if row is None:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
    row.is_resolved = resolved
    row.resolved_at = datetime.now(UTC) if resolved else None
    await db.commit()
    return {"ok": True, "is_resolved": resolved}


# ── 어드민 패널 전체 프로젝트 트리 — 선택 기업(X-Org-Id) 스코프와 무관하게 전 기업 반환 ──


class AdminProjectRow(BaseModel):
    id: str
    name: str
    organization_name: str | None
    team_id: str | None
    team_name: str | None


@router.get("/projects", response_model=list[AdminProjectRow])
async def list_all_projects(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """전 기업 프로젝트(어드민 패널 트리용).

    공용 GET /api/projects 는 어드민 선택 기업(X-Org-Id)으로 스코프되어 다른 기업 프로젝트가
    빠진다. 어드민 패널은 모든 기업을 한 화면에 보여줘야 하므로 스코프 없이 전체를 반환한다.
    """
    rows = await db.execute(
        text("""
            SELECT p.id, p.name, p.team_id,
                   o.name AS organization_name, t.name AS team_name
            FROM projects p
            LEFT JOIN organizations o ON o.id = p.organization_id
            LEFT JOIN teams t ON t.id = p.team_id
            WHERE p.status != 'DELETED' AND p.deleted_at IS NULL
            ORDER BY o.name NULLS LAST, p.created_at DESC
        """)
    )
    return [
        AdminProjectRow(
            id=str(r.id),
            name=r.name,
            organization_name=r.organization_name,
            team_id=str(r.team_id) if r.team_id else None,
            team_name=r.team_name,
        )
        for r in rows
    ]
