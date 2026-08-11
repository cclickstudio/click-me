# 센터(우측 통합 알림) 라우터 — management 이상감지 알림 + center 제안 알림 병합 조회·읽음·무시
"""알림 센터 백엔드 API — 두 저장소(management_notifications·center_suggestions)를 병합 조회.

스펙: docs/center/center-spec.md §5·§7·§8. 통합 마이그레이션 없이 병합 조회로 얹는다(open §3).
org 스코프: ADMIN은 X-Org-Id 헤더로 기업 선택, 그 외는 자기 소속 org. COMPANY는 제안 알림을
숨기고 management 이상감지 알림만 본다(스펙 §7). 세그먼트(안읽음·읽음·전체) 필터는 read_at
기준의 프론트 관심사라 백엔드는 미해결·미무시 항목을 통째로 내려준다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.access import assert_project_access
from core.auth import get_current_user, require_user_org
from core.center_suggestions import (
    dismiss_suggestion,
    list_center_suggestions,
    mark_suggestion_read,
)
from core.db import get_db
from core.models import Organization, User

router = APIRouter()


async def _resolve_org(user: User, db: AsyncSession, x_org_id: str | None) -> uuid.UUID | None:
    """org 스코프 해석. ADMIN은 X-Org-Id로 기업 선택(미선택·미존재면 None), 그 외는 자기 org."""
    role = (getattr(user, "role", "") or "").upper()
    if role == "ADMIN":
        if not x_org_id:
            return None  # 기업 미선택 → 프론트가 두 센터 disable + 안내(스펙 §7)
        try:
            org_uuid = uuid.UUID(x_org_id)
        except ValueError as exc:
            raise HTTPException(400, "X-Org-Id 형식 오류") from exc
        exists = await db.scalar(select(Organization.id).where(Organization.id == org_uuid))
        return org_uuid if exists is not None else None
    return await require_user_org(user, db)


def _ts(value: str | None) -> datetime:
    """정렬용 — ISO 문자열을 tz-aware datetime으로. 파싱 실패·None이면 최소값(맨 뒤)."""
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


def _norm_mgmt(m: dict) -> dict:
    """management 이상감지 알림 → 병합 목록 공통 형태(source=management)."""
    return {
        "source": "management",
        "id": m["id"],
        "project_id": m["project_id"],
        "project_name": m.get("project_name"),
        "kind": m.get("kind"),
        "campaign_id": m.get("campaign_id"),
        "payload": m.get("payload") or {},
        "read_at": m.get("read_at"),
        "resolution": m.get("resolution"),
        "followup_count": m.get("followup_count"),
        "created_at": m.get("last_notified_at"),
    }


@router.get("/notifications")
async def center_notifications(
    project_id: str | None = None,
    x_org_id: str | None = Header(None, alias="X-Org-Id"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """알림 센터 병합 목록 — management 이상감지 + center 제안(COMPANY는 제안 숨김).

    ADMIN이 기업 미선택이면 빈 목록 + org_selected=false(프론트가 안내·disable).
    """
    org = await _resolve_org(user, db, x_org_id)
    if org is None:
        return {"items": [], "unread_count": 0, "org_selected": False}
    role = (getattr(user, "role", "") or "").upper()

    # management 이상감지 알림(미해결) — 도메인 store 재사용(api 계층 컴포지션 패턴).
    from domain.management.remediation.notification_store import (  # noqa: PLC0415
        DbNotificationStore,
    )

    mgmt_items, mgmt_unread = await DbNotificationStore().list_for_org(
        str(org), project_id=project_id, include_resolved=False, limit=100
    )
    items = [_norm_mgmt(m) for m in mgmt_items]

    sugg_unread = 0
    if role != "COMPANY":  # COMPANY는 제안 알림 숨김(management만) — 스펙 §7
        suggestions = await list_center_suggestions(org_id=org, project_id=project_id, limit=100)
        items.extend(suggestions)
        sugg_unread = sum(1 for s in suggestions if not s.get("read_at"))

    items.sort(key=lambda x: _ts(x.get("created_at")), reverse=True)
    return {
        "items": items,
        "unread_count": int(mgmt_unread) + sugg_unread,
        "org_selected": True,
    }


@router.get("/sessions")
async def center_sessions(
    project_id: str | None = None,
    x_org_id: str | None = Header(None, alias="X-Org-Id"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """센터 채팅 통합 세션 목록 — org 전체 프로젝트(스펙 §6). project_id를 주면 그 프로젝트로 좁힘.

    ADMIN이 기업 미선택이면 빈 목록 + org_selected=false. 채팅 도메인 조회를 api 계층에서 컴포지션.
    """
    org = await _resolve_org(user, db, x_org_id)
    if org is None:
        return {"sessions": [], "org_selected": False}
    from domain.chat import history  # noqa: PLC0415

    role = (getattr(user, "role", "") or "").upper()
    if project_id:
        await assert_project_access(db, project_id, user)
    sessions = await history.list_sessions_for_org(
        db,
        org,
        project_id=project_id,
        user_id=user.id if role == "USER" else None,
        team_id=getattr(user, "team_id", None) if role == "USER" else None,
        restrict_user_projects=role == "USER",
    )
    return {"sessions": sessions, "org_selected": True}


@router.post("/suggestions/{suggestion_id}/read")
async def read_suggestion(
    suggestion_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """제안 알림 읽음 처리 — 아코디언을 열 때 호출(진입 일괄 아님, 스펙 §5.3)."""
    ok = await mark_suggestion_read(suggestion_id)
    return {"ok": ok}


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_center_suggestion(
    suggestion_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """제안 알림 무시 처리 — dismissed_at 설정으로 목록에서 제외 + dedup 슬롯 해제."""
    ok = await dismiss_suggestion(suggestion_id)
    return {"ok": ok}
