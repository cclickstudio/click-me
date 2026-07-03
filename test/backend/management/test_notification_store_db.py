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
