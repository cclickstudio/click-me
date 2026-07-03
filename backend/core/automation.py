# 자동화 실행 결과 공용 기록·조회 — APScheduler 워커(3도메인)가 core 경유로 사용
"""automation_runs 테이블의 기록·조회 경로(프론트 반영용 운영 저장소).

워커가 감지·진단한 결과를 프로젝트 단위로 남기고(record_automation_run), 프론트는
recent_automation_runs로 조회한다(탭 안 열려도 서버 결과를 읽음). 롱텀 메모리
(chat_execution_history=성공 수행만)와 별개 — 여기엔 자동 점검 결과가 남는다.
모두 best-effort — 기록·조회 실패가 워커/화면을 막지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import timedelta, timezone

from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.models import AutomationRun

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


async def record_automation_run(
    *,
    domain: str,
    job_name: str,
    title: str = "",
    body: str = "",
    project_id: str | None = None,
    org_id: str | None = None,
    status: str = "finding",
    severity: str | None = None,
    suggested_action: str | None = None,
    payload: dict | None = None,
    dedup_key: str | None = None,
) -> None:
    """자동화 결과 1건을 automation_runs에 적재(best-effort·비차단).

    dedup_key가 있고 미해결(resolved_at IS NULL) 동일 키가 이미 있으면 중복 통지 방지로 생략.
    project_id 없어도 남긴다(프론트 조회용 — 롱텀 메모리와 달리 프로젝트 귀속 불필요).
    """
    try:
        async with AsyncSessionLocal() as db:
            if dedup_key:
                existing = await db.execute(
                    select(AutomationRun.id)
                    .where(
                        AutomationRun.dedup_key == dedup_key,
                        AutomationRun.resolved_at.is_(None),
                    )
                    .limit(1)
                )
                if existing.first() is not None:
                    return  # 미해결 동일 알림 존재 → 재통지 안 함
            db.add(
                AutomationRun(
                    domain=domain,
                    job_name=job_name,
                    title=(title or "")[:200],
                    body=body or "",
                    project_id=_as_uuid(project_id),
                    org_id=_as_uuid(org_id),
                    status=status,
                    severity=severity,
                    suggested_action=suggested_action,
                    payload=payload or {},
                    dedup_key=dedup_key,
                )
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — 적재 실패가 워커를 막지 않게
        print(f"[automation] record error: {exc!r}")


async def recent_automation_runs(
    project_id: str | None = None,
    domain: str | None = None,
    limit: int = 20,
    unresolved_only: bool = False,
) -> list[dict]:
    """최근 자동화 결과 조회(최신순) — 프론트 반영용. 실패 시 빈 목록."""
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(AutomationRun)
            pid = _as_uuid(project_id)
            if pid is not None:
                stmt = stmt.where(AutomationRun.project_id == pid)
            if domain:
                stmt = stmt.where(AutomationRun.domain == domain)
            if unresolved_only:
                stmt = stmt.where(AutomationRun.resolved_at.is_(None))
            stmt = stmt.order_by(AutomationRun.created_at.desc()).limit(limit)
            rows = await db.execute(stmt)
            return [
                {
                    "id": str(r.id),
                    "domain": r.domain,
                    "job_name": r.job_name,
                    "status": r.status,
                    "severity": r.severity,
                    "title": r.title,
                    "body": r.body,
                    "suggested_action": r.suggested_action,
                    "payload": r.payload,
                    "created_at": r.created_at.astimezone(_KST).isoformat()
                    if r.created_at
                    else None,
                    "resolved_at": r.resolved_at.astimezone(_KST).isoformat()
                    if r.resolved_at
                    else None,
                }
                for r in rows.scalars()
            ]
    except Exception as exc:  # noqa: BLE001 — 조회 실패면 빈 목록
        print(f"[automation] query error: {exc!r}")
        return []
