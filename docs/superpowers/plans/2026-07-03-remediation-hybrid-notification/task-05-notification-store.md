# Task 5: DbNotificationStore (실 영속 계층)

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §1·§3
> **실행 규칙**: 백엔드 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 파일 첫 줄 한국어 헤더 주석 · 🅰 소유 파일 수정 금지.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Create: `backend/domain/management/remediation/notification_store.py`
- Test: `test/backend/management/test_notification_store_db.py` (신규, `MANAGEMENT_DB_TEST=1` 옵트인 — test_db_stores.py 패턴)

단위 보증은 Task 4·7·8의 fake 주입 테스트가 담당한다. 여기는 실 DB 왕복(부분 유니크·후속 UPDATE·auto_resolve)만 옵트인으로 확인.

- [ ] **Step 1: 구현**

`backend/domain/management/remediation/notification_store.py`:

```python
# 알림 영속 어댑터 — management_notifications CRUD·판정 신호 조회 (🅱)
"""PanelNotificationSink·알림 API가 쓰는 실제 DB 계층. 단위 보증은 fake 주입 테스트가,
여기는 옵트인 DB 통합 테스트(test_notification_store_db.py)가 담당한다."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError


class DbNotificationStore:
    def __init__(self, session_factory: Any = None) -> None:
        if session_factory is None:
            from core.db import AsyncSessionLocal  # noqa: PLC0415

            session_factory = AsyncSessionLocal
        self._sf = session_factory

    async def has_ignored(self, org_id: str, kind: str, dedup_key: str) -> bool:
        from core.models import ManagementNotification as N  # noqa: PLC0415

        async with self._sf() as db:
            row = await db.execute(
                select(N.id).where(
                    N.organization_id == uuid.UUID(org_id),
                    N.kind == kind,
                    N.dedup_key == dedup_key,
                    N.resolution == "ignored",
                ).limit(1)
            )
            return row.first() is not None

    async def open_state(self, org_id: str, kind: str, dedup_key: str) -> dict | None:
        from core.models import ManagementNotification as N  # noqa: PLC0415

        async with self._sf() as db:
            row = (
                await db.execute(
                    select(N.id, N.read_at, N.last_notified_at).where(
                        N.organization_id == uuid.UUID(org_id),
                        N.kind == kind,
                        N.dedup_key == dedup_key,
                        N.resolved_at.is_(None),
                    ).limit(1)
                )
            ).first()
            if row is None:
                return None
            return {"id": str(row[0]), "read_at": row[1], "last_notified_at": row[2]}

    async def insert(
        self,
        *,
        organization_id: str,
        project_id: str,
        campaign_id: str,
        kind: str,
        dedup_key: str,
        payload: dict,
        now: datetime,
    ) -> str:
        from domain.management.remediation.panel_sink import DedupRaceError  # noqa: PLC0415

        from core.models import ManagementNotification as N  # noqa: PLC0415

        async with self._sf() as db:
            n = N(
                organization_id=uuid.UUID(organization_id),
                project_id=uuid.UUID(project_id),
                campaign_id=campaign_id,
                kind=kind,
                dedup_key=dedup_key,
                payload=payload,
                last_notified_at=now,
            )
            db.add(n)
            try:
                await db.commit()
            except IntegrityError as exc:  # 부분 유니크 충돌 — 다른 워커 선점
                raise DedupRaceError() from exc
            return str(n.id)

    async def followup(self, notification_id: str, payload: dict, now: datetime) -> None:
        from core.models import ManagementNotification as N  # noqa: PLC0415

        async with self._sf() as db:
            await db.execute(
                update(N)
                .where(N.id == uuid.UUID(notification_id))
                .values(
                    read_at=None,  # 재-미열람화 — 배지 재점등
                    payload=payload,
                    followup_count=N.followup_count + 1,
                    last_notified_at=now,
                )
            )
            await db.commit()

    async def auto_resolve(
        self, org_id: str | None, kind: str, dedup_keys: list[str], now: datetime
    ) -> list[str]:
        """정상화된 미해결 알림을 auto_normal로 마킹 — 영향받은 org id 목록 반환(publish용)."""
        from core.models import ManagementNotification as N  # noqa: PLC0415

        async with self._sf() as db:
            cond = [N.kind == kind, N.dedup_key.in_(dedup_keys), N.resolved_at.is_(None)]
            if org_id is not None:
                cond.append(N.organization_id == uuid.UUID(org_id))
            rows = (await db.execute(select(N.id, N.organization_id).where(*cond))).all()
            if not rows:
                return []
            await db.execute(
                update(N)
                .where(N.id.in_([r[0] for r in rows]))
                .values(resolved_at=now, resolution="auto_normal")
            )
            await db.commit()
            return sorted({str(r[1]) for r in rows})

    async def list_for_org(
        self,
        org_id: str,
        *,
        project_id: str | None = None,
        unread_only: bool = False,
        include_resolved: bool = False,
        limit: int = 50,
        before: datetime | None = None,
        before_id: str | None = None,
    ) -> tuple[list[dict], int]:
        """(알림 목록, org 전체 미해결·미열람 수).

        정렬 (last_notified_at desc, id desc) — id 타이브레이커로 동률 순서 고정.
        커서는 (before, before_id) 복합 — 동률 행이 페이지 경계에서 누락되지 않는다.
        """
        from sqlalchemy import and_, or_  # noqa: PLC0415

        from core.models import ManagementNotification as N  # noqa: PLC0415
        from core.models import Project  # noqa: PLC0415

        async with self._sf() as db:
            cond = [N.organization_id == uuid.UUID(org_id)]
            if not include_resolved:
                cond.append(N.resolved_at.is_(None))
            if unread_only:
                cond.append(N.read_at.is_(None))
            if project_id:
                cond.append(N.project_id == uuid.UUID(project_id))
            if before is not None:
                if before_id is not None:
                    cond.append(
                        or_(
                            N.last_notified_at < before,
                            and_(
                                N.last_notified_at == before,
                                N.id < uuid.UUID(before_id),
                            ),
                        )
                    )
                else:
                    cond.append(N.last_notified_at < before)
            rows = (
                await db.execute(
                    select(N, Project.name)
                    .join(Project, Project.id == N.project_id)
                    .where(*cond)
                    .order_by(N.last_notified_at.desc(), N.id.desc())
                    .limit(min(limit, 200))
                )
            ).all()
            unread = (
                await db.execute(
                    select(func.count()).select_from(N).where(
                        N.organization_id == uuid.UUID(org_id),
                        N.resolved_at.is_(None),
                        N.read_at.is_(None),
                    )
                )
            ).scalar_one()
            items = [
                {
                    "id": str(n.id),
                    "project_id": str(n.project_id),
                    "project_name": pname,
                    "campaign_id": n.campaign_id,
                    "kind": n.kind,
                    "payload": n.payload,
                    "read_at": n.read_at.isoformat() if n.read_at else None,
                    "resolved_at": n.resolved_at.isoformat() if n.resolved_at else None,
                    "resolution": n.resolution,
                    "followup_count": n.followup_count,
                    "last_notified_at": n.last_notified_at.isoformat(),
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                }
                for n, pname in rows
            ]
            return items, int(unread)

    async def get(self, notification_id: str) -> dict | None:
        from core.models import ManagementNotification as N  # noqa: PLC0415

        async with self._sf() as db:
            n = (
                await db.execute(select(N).where(N.id == uuid.UUID(notification_id)))
            ).scalars().first()
            if n is None:
                return None
            return {
                "id": str(n.id),
                "organization_id": str(n.organization_id),
                "project_id": str(n.project_id),
                "campaign_id": n.campaign_id,
                "kind": n.kind,
                "payload": n.payload,
                "read_at": n.read_at,
                "resolved_at": n.resolved_at,
                "resolution": n.resolution,
                "consult_session_id": (
                    str(n.consult_session_id) if n.consult_session_id else None
                ),
            }

    async def mark_read(self, org_id: str, ids: list[str], now: datetime) -> int:
        from core.models import ManagementNotification as N  # noqa: PLC0415

        async with self._sf() as db:
            res = await db.execute(
                update(N)
                .where(
                    N.organization_id == uuid.UUID(org_id),
                    N.id.in_([uuid.UUID(i) for i in ids]),
                    N.read_at.is_(None),
                )
                .values(read_at=now)
            )
            await db.commit()
            return res.rowcount or 0

    async def resolve(
        self, org_id: str, notification_id: str, resolution: str, now: datetime
    ) -> bool:
        from core.models import ManagementNotification as N  # noqa: PLC0415

        async with self._sf() as db:
            res = await db.execute(
                update(N)
                .where(
                    N.organization_id == uuid.UUID(org_id),
                    N.id == uuid.UUID(notification_id),
                    N.resolved_at.is_(None),
                )
                .values(resolved_at=now, resolution=resolution)
            )
            await db.commit()
            return bool(res.rowcount)

    async def claim_consult_session(self, notification_id: str, session_id: str) -> bool:
        """CAS — consult_session_id가 비어 있을 때만 세팅. 승자 True(심기 담당)."""
        from core.models import ManagementNotification as N  # noqa: PLC0415

        async with self._sf() as db:
            res = await db.execute(
                update(N)
                .where(N.id == uuid.UUID(notification_id), N.consult_session_id.is_(None))
                .values(consult_session_id=uuid.UUID(session_id))
            )
            await db.commit()
            return bool(res.rowcount)

    async def release_consult_session(self, notification_id: str, session_id: str) -> None:
        """보상 롤백 — 심기 실패 시 CAS를 되돌린다(빈 세션 영구 안내 방지)."""
        from core.models import ManagementNotification as N  # noqa: PLC0415

        async with self._sf() as db:
            await db.execute(
                update(N)
                .where(
                    N.id == uuid.UUID(notification_id),
                    N.consult_session_id == uuid.UUID(session_id),
                )
                .values(consult_session_id=None)
            )
            await db.commit()
```

- [ ] **Step 2: 옵트인 DB 통합 테스트 작성**

`test/backend/management/test_notification_store_db.py`:

```python
"""알림 store DB 통합 — 옵트인 (실 Postgres + Alembic 0005 필요).

기본 skip. `MANAGEMENT_DB_TEST=1` + `alembic upgrade head` 후 throwaway DB에서만.
부분 유니크(dedup race)·후속 UPDATE·auto_resolve 왕복을 실 DB에서 확인한다.
사전 조건: 테스트 org/project id를 MANAGEMENT_DB_TEST_ORG_ID / _PROJECT_ID 환경변수로 주입.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("MANAGEMENT_DB_TEST") != "1",
    reason="DB 통합 — MANAGEMENT_DB_TEST=1 + Alembic 0005 적용 시에만 (옵트인)",
)


def test_partial_unique_blocks_duplicate_open_row():
    """같은 (org,kind,dedup) 미해결 2건째 INSERT는 DedupRaceError — resolve 후엔 재INSERT 허용."""
    from domain.management.remediation.notification_store import DbNotificationStore
    from domain.management.remediation.panel_sink import KIND, DedupRaceError

    store = DbNotificationStore()
    org = os.environ["MANAGEMENT_DB_TEST_ORG_ID"]
    proj = os.environ["MANAGEMENT_DB_TEST_PROJECT_ID"]
    key = f"camp-{uuid.uuid4().hex[:8]}:no_delivery"

    async def run():
        now = datetime.now(UTC)
        nid = await store.insert(
            organization_id=org, project_id=proj, campaign_id="c1",
            kind=KIND, dedup_key=key, payload={"x": 1}, now=now,
        )
        with pytest.raises(DedupRaceError):
            await store.insert(
                organization_id=org, project_id=proj, campaign_id="c1",
                kind=KIND, dedup_key=key, payload={"x": 2}, now=now,
            )
        # 후속 UPDATE — read_at 초기화·카운트 증가
        await store.mark_read(org, [nid], now)
        await store.followup(nid, {"x": 3}, now)
        state = await store.open_state(org, KIND, key)
        assert state is not None and state["read_at"] is None
        # auto_resolve 후 재INSERT 허용
        orgs = await store.auto_resolve(org, KIND, [key], now)
        assert orgs == [org]
        await store.insert(
            organization_id=org, project_id=proj, campaign_id="c1",
            kind=KIND, dedup_key=key, payload={"x": 4}, now=now,
        )

    asyncio.run(run())
```

- [ ] **Step 3: 단위 스위트 회귀(wiring panel 분기 포함) + Ruff + 커밋**

```bash
cd backend && uv run pytest ../test/backend/management -q
cd backend && uv run ruff format . && uv run ruff check . --fix && cd ..
git add backend/domain/management/remediation/notification_store.py test/backend/management/test_notification_store_db.py
git commit -m "add: 알림 영속 어댑터 DbNotificationStore + 옵트인 DB 통합 테스트"
```
