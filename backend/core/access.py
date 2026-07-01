# 라우트 공통 인가 — 프로젝트 소유권(org/team/생성자) 기반 리소스 접근 검증.
"""chat/generator/simulation/personas 라우트에서 재사용하는 인가 헬퍼.

projects.py의 _project_access_ok 패턴을 분리해 공유한다. 세션·시뮬·생성 같은
하위 리소스는 부모 프로젝트로 조인해 접근 권한을 판정한다(미존재 404, 권한없음 403).
"""

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import OrganizationMember, User


async def get_user_org_id(user: User, db: AsyncSession) -> str:
    member = await db.scalar(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    )
    if not member:
        raise HTTPException(status_code=404, detail="소속 조직을 찾을 수 없습니다.")
    return str(member.organization_id)


def project_access_ok(org_id, team_id, created_by, user: User, user_org_id: str) -> bool:
    """프로젝트 메타(org/team/생성자)로 현재 사용자의 접근 가능 여부를 판정.

    ADMIN=전체, COMPANY=같은 조직, USER=같은 팀(미배정 프로젝트는 생성자 본인만).
    """
    role = user.role.upper()
    if role == "ADMIN":
        return True
    if str(org_id) != user_org_id:
        return False
    if role == "COMPANY":
        return True
    if team_id is not None:
        return bool(user.team_id) and str(team_id) == str(user.team_id)
    return str(created_by) == str(user.id)


async def _assert_meta_access(db: AsyncSession, meta, user: User, missing_detail: str) -> None:
    """org/team/created_by 메타 행으로 접근을 판정. meta가 None이면 404."""
    if meta is None:
        raise HTTPException(status_code=404, detail=missing_detail)
    if user.role.upper() != "ADMIN":
        org_id = await get_user_org_id(user, db)
        if not project_access_ok(meta.organization_id, meta.team_id, meta.created_by, user, org_id):
            raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")


async def assert_project_access(db: AsyncSession, project_id: str, user: User) -> None:
    """프로젝트가 존재하고 현재 사용자가 접근 가능한지 확인(미존재 404, 권한없음 403)."""
    row = await db.execute(
        text("SELECT organization_id, team_id, created_by FROM projects WHERE id = :pid"),
        {"pid": project_id},
    )
    await _assert_meta_access(db, row.fetchone(), user, "프로젝트를 찾을 수 없습니다.")


async def assert_session_access(db: AsyncSession, session_id: str, user: User) -> None:
    """채팅 세션 접근 — 세션이 프로젝트에 귀속됐으면 그 프로젝트 권한으로 판정.

    project_id가 없는(레거시·전역) 세션은 로그인만 확인하고 통과시킨다.
    """
    row = await db.execute(
        text("SELECT project_id FROM chat_sessions WHERE id = :sid"),
        {"sid": session_id},
    )
    s = row.fetchone()
    if not s:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    if s.project_id is not None:
        await assert_project_access(db, str(s.project_id), user)


async def assert_message_access(db: AsyncSession, message_id: str, user: User) -> None:
    """메시지 → 세션 → 프로젝트로 접근을 판정."""
    row = await db.execute(
        text(
            "SELECT cs.project_id FROM chat_messages cm "
            "JOIN chat_sessions cs ON cs.id = cm.session_id WHERE cm.id = :mid"
        ),
        {"mid": message_id},
    )
    m = row.fetchone()
    if not m:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")
    if m.project_id is not None:
        await assert_project_access(db, str(m.project_id), user)


async def assert_simulation_access(db: AsyncSession, simulation_id: str, user: User) -> None:
    """시뮬레이션 → 광고 → 프로젝트로 접근을 판정."""
    row = await db.execute(
        text(
            "SELECT p.organization_id, p.team_id, p.created_by "
            "FROM simulations s JOIN ads a ON a.id = s.ad_id "
            "JOIN projects p ON p.id = a.project_id WHERE s.id = :sid"
        ),
        {"sid": simulation_id},
    )
    await _assert_meta_access(db, row.fetchone(), user, "시뮬레이션을 찾을 수 없습니다.")


async def assert_generation_access(db: AsyncSession, generation_id: str, user: User) -> None:
    """생성 내역 → 프로젝트로 접근을 판정.

    project_id가 없는(시스템·improve) 생성은 로그인만 확인하고 통과시킨다.
    """
    row = await db.execute(
        text(
            "SELECT g.project_id, p.organization_id, p.team_id, p.created_by "
            "FROM ad_generations g LEFT JOIN projects p ON p.id = g.project_id "
            "WHERE g.id = :gid"
        ),
        {"gid": generation_id},
    )
    r = row.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="제너레이터 내역을 찾을 수 없습니다.")
    if r.project_id is not None:
        await _assert_meta_access(db, r, user, "제너레이터 내역을 찾을 수 없습니다.")
