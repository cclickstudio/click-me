"""공용 자동화 저장소(automation_runs) — 기록·dedup·조회 라운드트립.

DB 통합이라 기본 skip(옵트인) — 실행: MANAGEMENT_DB_TEST=1 (automation_runs 테이블 필요).
test_db_stores와 동일 관례. 생성 행은 distinctive 키로 만들고 finally에서 삭제(오염 방지).
단일 test에 모아 함수별 이벤트 루프 공유 이슈를 피한다(asyncio.run 1회).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import delete, select

pytestmark = pytest.mark.skipif(
    os.getenv("MANAGEMENT_DB_TEST") != "1",
    reason="DB 통합 — MANAGEMENT_DB_TEST=1 + automation_runs 테이블 시에만 (옵트인)",
)


def test_automation_runs_record_dedup_query_roundtrip():
    from core.automation import recent_automation_runs, record_automation_run
    from core.db import AsyncSessionLocal
    from core.models import AutomationRun

    key = f"pytest:{uuid.uuid4()}"
    tag = f"pytest-noproj-{uuid.uuid4()}"

    async def run():
        try:
            # ① dedup — 미해결 동일 키 재기록은 생략(1건 유지).
            await record_automation_run(
                domain="management", job_name="test_rule", title="A", body="본문", dedup_key=key
            )
            await record_automation_run(
                domain="management", job_name="test_rule", title="B", dedup_key=key
            )
            # ② 프로젝트 귀속 없어도 남는다(프론트 조회용).
            await record_automation_run(domain="simulation", job_name="x", title=tag)

            async with AsyncSessionLocal() as db:
                dedup_rows = (
                    (await db.execute(select(AutomationRun).where(AutomationRun.dedup_key == key)))
                    .scalars()
                    .all()
                )
                noproj_rows = (
                    (await db.execute(select(AutomationRun).where(AutomationRun.title == tag)))
                    .scalars()
                    .all()
                )
            assert len(dedup_rows) == 1  # dedup 작동
            assert dedup_rows[0].title == "A"
            assert len(noproj_rows) == 1
            assert noproj_rows[0].project_id is None
            assert noproj_rows[0].domain == "simulation"

            # ③ 조회 API에 최신순으로 뜬다.
            runs = await recent_automation_runs(limit=200)
            ids = {r["id"] for r in runs}
            assert str(dedup_rows[0].id) in ids
            assert str(noproj_rows[0].id) in ids
        finally:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(AutomationRun).where(AutomationRun.dedup_key == key))
                await db.execute(delete(AutomationRun).where(AutomationRun.title == tag))
                await db.commit()

    asyncio.run(run())
