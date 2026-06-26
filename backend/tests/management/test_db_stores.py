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


def test_proposal_store_save_get_roundtrip_and_atomic_claim():
    from domain.management.execution.proposal_builder import (
        build_action_proposal_from_diagnosis,
    )
    from domain.management.execution.service.proposal_store import DbProposalStore
    from tests.management.test_chat_execution_bridge import _ok_anomaly_dx

    store = DbProposalStore()

    async def run():
        p = build_action_proposal_from_diagnosis(
            _ok_anomaly_dx(),
            tenant_id=f"org-{uuid.uuid4().hex[:8]}",
            ad_account_id="act_1",
            campaign_id="camp_1",
            expected_state_version="state_v1",
            approval_policy_version="v1",
        )
        await store.save(p)
        got = await store.get(p.proposal_id)
        assert got is not None
        assert got.proposal_hash == p.proposal_hash  # 해시 보존 (왕복 무손실)

        # 게이트 #1 — 실 Postgres에서 동시 10회 try_claim → 정확히 1건만 True.
        claims = await asyncio.gather(*[store.try_claim(p.proposal_id) for _ in range(10)])
        assert sum(1 for c in claims if c is True) == 1
        assert sum(1 for c in claims if c is False) == 9

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


def test_chat_card_persist_and_session_reload_round_trip():
    # 스펙3 Task8 — 결과 카드 적재(_persist_card) → 세션 thread_id로 재조회 시 동일 카드 복원.
    import json

    from sqlalchemy import select

    from api.routers.chat import _content_to_card
    from api.routers.chat_management import _persist_card
    from core.db import AsyncSessionLocal
    from core.models import ManagementChatMessage
    from domain.management.assistant.chat_cards.models import (
        ChatCard,
        ExecutionResultSection,
    )

    thread_id = f"mgmt-{uuid.uuid4().hex[:8]}"
    card = ChatCard(
        type="management",
        status="ok",
        sections=[
            ExecutionResultSection(
                title="집행 결과",
                action_type="DECREASE_BUDGET",
                result_status="success",
                proposal_id=f"prop-{uuid.uuid4().hex[:8]}",
                summary="집행 완료",
            )
        ],
    )

    async def run():
        await _persist_card(thread_id, card)
        async with AsyncSessionLocal() as session:
            rows = (
                (
                    await session.execute(
                        select(ManagementChatMessage)
                        .where(ManagementChatMessage.thread_id == thread_id)
                        .order_by(ManagementChatMessage.created_at)
                    )
                )
                .scalars()
                .all()
            )
        assert len(rows) == 1
        assert rows[0].role == "assistant"
        reloaded = _content_to_card(rows[0].content)
        assert reloaded == card.model_dump(mode="json")
        # content 자체도 무손실 직렬화여야 한다.
        assert json.loads(rows[0].content) == card.model_dump(mode="json")

    asyncio.run(run())
