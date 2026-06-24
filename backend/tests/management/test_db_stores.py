"""DB 영속 어댑터 통합 테스트 — 옵트인 (실 Postgres + Alembic 007 필요).

기본 skip. 실행하려면 테스트용 DB로 `MANAGEMENT_DB_TEST=1` 설정 + `alembic upgrade head`.
테스트 행을 남기므로 throwaway DB에서만 돌린다. 단위 보증은 test_executor_gates(async
InMemory)가 담당하고, 여기선 DB 어댑터의 원자적 선점·replay·감사 왕복만 확인한다.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

import pytest

from domain.management.contracts.enums import ResultStatus
from domain.management.contracts.schemas import ActionResult
from domain.management.execution.audit_log import AuditEvent

pytestmark = pytest.mark.skipif(
    os.getenv("MANAGEMENT_DB_TEST") != "1",
    reason="DB 통합 — MANAGEMENT_DB_TEST=1 + Alembic 007 적용 시에만 (옵트인)",
)


def test_reserve_is_atomic_and_result_replays():
    from domain.management.execution.db_stores import DbIdempotencyStore

    store = DbIdempotencyStore()
    key = f"test-{uuid.uuid4().hex}"
    approval_id = f"appr-{uuid.uuid4().hex[:8]}"

    async def run():
        assert await store.reserve(key, approval_id) is True
        assert await store.reserve(key, approval_id) is False  # 중복 선점 = 거부 (게이트 #1)
        assert await store.get_result(key) is None
        result = ActionResult(
            result_id="res-1",
            approval_id=approval_id,
            status=ResultStatus.SUCCESS,
            idempotency_key=key,
            executed_at=datetime.now(UTC),
        )
        await store.save_result(key, result)
        replayed = await store.get_result(key)
        assert replayed is not None
        assert replayed.result_id == "res-1"

    asyncio.run(run())


def test_audit_append_and_for_approval_with_masking():
    from domain.management.execution.db_stores import DbAuditSink

    sink = DbAuditSink()
    approval_id = f"appr-{uuid.uuid4().hex[:8]}"

    async def run():
        await sink.append(
            AuditEvent(
                category="executor.completed",
                tenant_id="org-t",
                proposal_id="prop-t",
                approval_id=approval_id,
                payload={"access_token": "SECRET_VALUE", "ok": 1},
            )
        )
        events = await sink.for_approval(approval_id)
        assert len(events) == 1
        assert events[0].category == "executor.completed"
        assert events[0].payload["access_token"] == "***"  # 게이트 #8 마스킹
        assert events[0].payload["ok"] == 1

    asyncio.run(run())
