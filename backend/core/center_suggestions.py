# 센터 제안 알림 공용 기록·조회 — 잡 완료 직후 인라인으로 크로스도메인 제안을 적재
"""center_suggestions 테이블의 기록·조회 경로(센터 알림용 제안 저장소).

시뮬/제너 잡이 끝난 직후 인라인으로 제안 1건을 남기고(create_center_suggestion),
알림 센터가 management 이상감지 알림과 병합 조회한다. automation.py와 같은
best-effort 원칙 — 적재·조회 실패가 잡/화면을 막지 않는다. 스펙: docs/center/center-spec.md §5·§8.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from core.db import AsyncSessionLocal
from core.models import CenterSuggestion, Project

_KST = timezone(timedelta(hours=9))


def _as_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


async def create_center_suggestion(
    *,
    suggestion_type: str,
    organization_id: str | uuid.UUID,
    project_id: str | uuid.UUID,
    reason: str | None = None,
    source_sim_id: str | uuid.UUID | None = None,
    source_gen_id: str | uuid.UUID | None = None,
    payload: dict | None = None,
    dedup_key: str | None = None,
) -> None:
    """제안 알림 1건을 center_suggestions에 적재(best-effort·비차단).

    dedup_key가 있고 미처리(dismissed_at IS NULL) 동일 키가 이미 있으면 중복 제안을 생략한다.
    DB 부분 유니크 인덱스(uq_center_suggest_open_dedup)가 최종 백스톱 — 경합 IntegrityError는 무시.
    project_id는 NOT NULL이라 파싱 실패면 생략, org는 없으면 project에서 해석한다.
    """
    org = _as_uuid(organization_id)
    proj = _as_uuid(project_id)
    if proj is None:
        return
    try:
        async with AsyncSessionLocal() as db:
            if org is None:
                # request에 org가 없는 경로(제너레이터 등) — 프로젝트에서 org를 해석.
                org = await db.scalar(select(Project.organization_id).where(Project.id == proj))
                if org is None:
                    return
            if dedup_key:
                existing = await db.execute(
                    select(CenterSuggestion.id)
                    .where(
                        CenterSuggestion.dedup_key == dedup_key,
                        CenterSuggestion.dismissed_at.is_(None),
                    )
                    .limit(1)
                )
                if existing.first() is not None:
                    return  # 미처리 동일 제안 존재 → 재제안 안 함
            db.add(
                CenterSuggestion(
                    suggestion_type=suggestion_type,
                    reason=(reason or None) and reason[:200],
                    organization_id=org,
                    project_id=proj,
                    source_sim_id=_as_uuid(source_sim_id),
                    source_gen_id=_as_uuid(source_gen_id),
                    payload=payload or {},
                    dedup_key=(dedup_key or None) and dedup_key[:200],
                )
            )
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()  # 동시 적재 경합 → 이미 있는 것으로 간주
    except Exception as exc:  # noqa: BLE001 — 적재 실패가 잡을 막지 않게
        print(f"[center] suggestion create error: {exc!r}")


def _serialize(s: CenterSuggestion) -> dict:
    """제안 1건을 알림 센터 병합 목록용 dict로 직렬화(management 알림과 병합 가능한 공통 형태)."""
    return {
        "id": str(s.id),
        "source": "center_suggestion",
        "suggestion_type": s.suggestion_type,
        "reason": s.reason,
        "organization_id": str(s.organization_id),
        "project_id": str(s.project_id),
        "source_sim_id": str(s.source_sim_id) if s.source_sim_id else None,
        "source_gen_id": str(s.source_gen_id) if s.source_gen_id else None,
        "payload": s.payload,
        "read_at": s.read_at.astimezone(_KST).isoformat() if s.read_at else None,
        "created_at": s.created_at.astimezone(_KST).isoformat() if s.created_at else None,
    }


async def list_center_suggestions(
    *,
    org_id: str | uuid.UUID,
    project_id: str | uuid.UUID | None = None,
    include_dismissed: bool = False,
    limit: int = 50,
) -> list[dict]:
    """제안 알림 조회(최신순) — org 스코프 필수. project_id None이면 org 전체. 실패 시 빈 목록."""
    org = _as_uuid(org_id)
    if org is None:
        return []
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(CenterSuggestion).where(CenterSuggestion.organization_id == org)
            pid = _as_uuid(project_id)
            if pid is not None:
                stmt = stmt.where(CenterSuggestion.project_id == pid)
            if not include_dismissed:
                stmt = stmt.where(CenterSuggestion.dismissed_at.is_(None))
            stmt = stmt.order_by(CenterSuggestion.created_at.desc()).limit(limit)
            rows = await db.execute(stmt)
            return [_serialize(s) for s in rows.scalars()]
    except Exception as exc:  # noqa: BLE001 — 조회 실패면 빈 목록
        print(f"[center] suggestion query error: {exc!r}")
        return []


async def mark_suggestion_read(suggestion_id: str | uuid.UUID) -> bool:
    """제안 알림 1건 읽음 처리(아코디언 열 때 호출). 이미 읽음이면 유지. 성공 여부 반환."""
    sid = _as_uuid(suggestion_id)
    if sid is None:
        return False
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(CenterSuggestion)
                .where(CenterSuggestion.id == sid, CenterSuggestion.read_at.is_(None))
                .values(read_at=datetime.now(_KST))
            )
            await db.commit()
            return True
    except Exception as exc:  # noqa: BLE001
        print(f"[center] suggestion mark-read error: {exc!r}")
        return False


async def dismiss_suggestion(suggestion_id: str | uuid.UUID) -> bool:
    """제안 알림 1건 무시 처리(dismissed_at 설정 → dedup 슬롯 해제). 성공 여부 반환."""
    sid = _as_uuid(suggestion_id)
    if sid is None:
        return False
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(CenterSuggestion)
                .where(CenterSuggestion.id == sid, CenterSuggestion.dismissed_at.is_(None))
                .values(dismissed_at=datetime.now(_KST))
            )
            await db.commit()
            return True
    except Exception as exc:  # noqa: BLE001
        print(f"[center] suggestion dismiss error: {exc!r}")
        return False
