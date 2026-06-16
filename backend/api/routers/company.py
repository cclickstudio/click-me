"""기업(COMPANY) 전용 API — 소속 USER 승인/관리."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, hash_password
from core.db import get_db
from core.models import Organization, OrganizationMember, Team, User

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
    login_id: str
    created_at: datetime


class MemberRow(BaseModel):
    member_id: str
    user_id: str
    user_name: str
    login_id: str
    status: str
    team_id: str | None = None
    phone_num: str | None = None
    user_email: str | None = None
    joined_at: datetime | None
    created_at: datetime


class TeamRow(BaseModel):
    id: str
    name: str
    member_count: int
    created_at: datetime


class CreateTeam(BaseModel):
    name: str


class AssignTeam(BaseModel):
    team_id: str | None = None  # None이면 미배정으로


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
            login_id=u.login_id,
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


class UpdateMember(BaseModel):
    name: str | None = None
    password: str | None = None  # 값이 있으면 비밀번호 재설정


@router.patch("/members/{member_id}", response_model=MemberRow)
async def update_member(
    member_id: str,
    body: UpdateMember,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """COMPANY가 소속 팀원의 이름·비밀번호를 수정. (역할·조직은 변경하지 않음)"""
    if current_user.role != "COMPANY":
        raise HTTPException(
            status_code=403, detail="팀원 계정 수정은 기업(COMPANY) 계정만 가능합니다."
        )
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

    if body.name is not None and body.name.strip():
        user.name = body.name.strip()
    if body.password:
        if len(body.password) < 8:
            raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다.")
        user.password_hash = hash_password(body.password)

    await db.flush()
    await db.refresh(member)
    return MemberRow(
        member_id=str(member.id),
        user_id=str(user.id),
        user_name=user.name,
        login_id=user.login_id,
        status=member.status,
        team_id=str(user.team_id) if user.team_id else None,
        joined_at=member.joined_at,
        created_at=member.created_at,
    )


@router.delete("/members/{member_id}")
async def delete_member(
    member_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """팀원 제거 — 멤버십과 유저 계정을 삭제한다.

    멤버가 만든 프로젝트·시뮬·생성 콘텐츠는 회사에 남기고 소유권을
    삭제 실행자(현재 사용자)에게 이전한다. (created_by FK가 NOT NULL이라 NULL 불가)
    """
    org = await _get_company_org(current_user, db)

    member = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == org.id,
        )
    )
    if not member:
        raise HTTPException(status_code=404, detail="멤버를 찾을 수 없습니다.")

    uid = str(member.user_id)
    if uid == str(current_user.id):
        raise HTTPException(status_code=400, detail="본인 계정은 제거할 수 없습니다.")

    reassign = {"uid": uid, "actor": str(current_user.id)}
    # 멤버가 만든 콘텐츠 소유권 이전 (created_by NOT NULL → 작업자에게)
    for table in ("projects", "simulations", "ads", "ad_generations"):
        await db.execute(
            text(f"UPDATE {table} SET created_by = :actor WHERE created_by = :uid"), reassign
        )
    # 교차 참조 정리 후 멤버십·유저 삭제
    await db.execute(
        text("UPDATE organization_members SET invited_by = NULL WHERE invited_by = :uid"),
        {"uid": uid},
    )
    await db.execute(
        text("UPDATE users SET created_by = NULL WHERE created_by = :uid"), {"uid": uid}
    )
    await db.execute(text("DELETE FROM organization_members WHERE id = :mid"), {"mid": member_id})
    await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
    await db.commit()
    return {"ok": True}


class CreateMember(BaseModel):
    name: str
    login_id: str
    password: str
    team_id: str | None = None  # 생성 시 팀 지정(선택)


@router.post("/members", response_model=MemberRow, status_code=201)
async def create_member(
    body: CreateMember,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """COMPANY가 소속 USER(팀원) 계정을 직접 생성. 승인 없이 바로 ACTIVE."""
    if current_user.role != "COMPANY":
        raise HTTPException(
            status_code=403, detail="팀원 계정 생성은 기업(COMPANY) 계정만 가능합니다."
        )
    org = await _get_company_org(current_user, db)

    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다.")
    if await db.scalar(select(User).where(User.login_id == body.login_id)):
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")

    team_uuid = None
    if body.team_id:
        team = await db.scalar(
            select(Team).where(Team.id == body.team_id, Team.organization_id == org.id)
        )
        if not team:
            raise HTTPException(status_code=404, detail="존재하지 않는 팀입니다.")
        team_uuid = team.id

    user = User(
        login_id=body.login_id,
        password_hash=hash_password(body.password),
        name=body.name,
        role="USER",
        status="ACTIVE",
        must_change_password=True,  # 발급된 임시 비번 → 최초 로그인 시 변경 유도
        team_id=team_uuid,
    )
    db.add(user)
    await db.flush()

    member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role="MEMBER",
        invited_by=current_user.id,
        status="ACTIVE",
        joined_at=datetime.utcnow(),
    )
    db.add(member)
    await db.flush()
    await db.refresh(member)

    return MemberRow(
        member_id=str(member.id),
        user_id=str(user.id),
        user_name=user.name,
        login_id=user.login_id,
        status=member.status,
        team_id=str(user.team_id) if user.team_id else None,
        joined_at=member.joined_at,
        created_at=member.created_at,
    )


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
            login_id=u.login_id,
            status=m.status,
            team_id=str(u.team_id) if u.team_id else None,
            phone_num=u.phone_num,
            user_email=u.user_email,
            joined_at=m.joined_at,
            created_at=m.created_at,
        )
        for m, u in rows.all()
    ]


# ── 팀 관리 (칸반) ────────────────────────────


@router.get("/teams", response_model=list[TeamRow])
async def list_teams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """소속 조직의 팀 목록 + 팀별 인원수."""
    org = await _get_company_org(current_user, db)
    rows = await db.execute(
        text("""
            SELECT t.id, t.name, t.created_at, COUNT(u.id) AS member_count
            FROM teams t
            LEFT JOIN users u ON u.team_id = t.id
            WHERE t.organization_id = :org
            GROUP BY t.id, t.name, t.created_at
            ORDER BY t.created_at
        """),
        {"org": org.id},
    )
    return [
        TeamRow(
            id=str(r.id),
            name=r.name,
            member_count=r.member_count,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/teams", response_model=TeamRow, status_code=201)
async def create_team(
    body: CreateTeam,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """팀 생성 (COMPANY 전용)."""
    if current_user.role != "COMPANY":
        raise HTTPException(status_code=403, detail="팀 관리는 기업(COMPANY) 계정만 가능합니다.")
    org = await _get_company_org(current_user, db)
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="팀 이름을 입력해주세요.")
    team = Team(organization_id=org.id, name=body.name.strip())
    db.add(team)
    await db.flush()
    await db.refresh(team)
    return TeamRow(id=str(team.id), name=team.name, member_count=0, created_at=team.created_at)


@router.delete("/teams/{team_id}")
async def delete_team(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """팀 삭제 (COMPANY 전용). 소속 팀원은 미배정으로 되돌린다."""
    if current_user.role != "COMPANY":
        raise HTTPException(status_code=403, detail="팀 관리는 기업(COMPANY) 계정만 가능합니다.")
    org = await _get_company_org(current_user, db)
    team = await db.scalar(select(Team).where(Team.id == team_id, Team.organization_id == org.id))
    if not team:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")
    await db.execute(text("UPDATE users SET team_id = NULL WHERE team_id = :tid"), {"tid": team_id})
    await db.execute(text("DELETE FROM teams WHERE id = :tid"), {"tid": team_id})
    return {"ok": True}


@router.patch("/members/{member_id}/team")
async def assign_member_team(
    member_id: str,
    body: AssignTeam,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """팀원을 팀에 배정/이동 (칸반 드래그). team_id가 None이면 미배정으로."""
    if current_user.role != "COMPANY":
        raise HTTPException(status_code=403, detail="팀 관리는 기업(COMPANY) 계정만 가능합니다.")
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

    if body.team_id:
        team = await db.scalar(
            select(Team).where(Team.id == body.team_id, Team.organization_id == org.id)
        )
        if not team:
            raise HTTPException(status_code=404, detail="존재하지 않는 팀입니다.")
        user.team_id = team.id
    else:
        user.team_id = None
    return {"ok": True}


class OrgInfo(BaseModel):
    id: str
    name: str
    plan: str
    status: str


@router.get("/org", response_model=OrgInfo)
async def get_my_org(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """내 소속 조직 정보 (USER/COMPANY 모두 조회 가능, Read 전용)."""
    org = await _get_company_org(current_user, db)
    return OrgInfo(id=str(org.id), name=org.name, plan=org.plan, status=org.status)


@router.get("/my-team-members")
async def my_team_members(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """현재 유저가 속한 팀의 멤버 이름 목록 (프로젝트 패널 TEAM 필터용). 팀 없으면 빈 목록."""
    if not current_user.team_id:
        return {"team_id": None, "member_names": []}
    rows = await db.execute(select(User.name).where(User.team_id == current_user.team_id))
    return {"team_id": str(current_user.team_id), "member_names": list(rows.scalars().all())}


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
            WHERE s.organization_id = :org_id AND s.deleted_at IS NULL
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
            WHERE p.organization_id = :org_id AND g.deleted_at IS NULL
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
