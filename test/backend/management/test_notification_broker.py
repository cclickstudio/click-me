# 알림 SSE 브로커 테스트 — 구독/발행/드랍 정책/해제 정리
from __future__ import annotations

import pytest

from domain.management.remediation import broker


@pytest.fixture(autouse=True)
def _clean():
    broker._subscribers.clear()
    yield
    broker._subscribers.clear()


@pytest.mark.asyncio
async def test_publish_reaches_subscriber():
    q = broker.subscribe("org-1")
    broker.publish("org-1")
    assert q.get_nowait() == "changed"


@pytest.mark.asyncio
async def test_publish_other_org_not_received():
    q = broker.subscribe("org-1")
    broker.publish("org-2")
    assert q.empty()


@pytest.mark.asyncio
async def test_full_queue_drops_without_error():
    q = broker.subscribe("org-1")
    for _ in range(20):  # maxsize=8 초과 — 예외 없이 드랍돼야 함
        broker.publish("org-1")
    assert q.qsize() == 8  # 미소비 신호가 남아 있으므로 refetch는 보장됨(무손실)


@pytest.mark.asyncio
async def test_unsubscribe_cleans_registry():
    q = broker.subscribe("org-1")
    broker.unsubscribe("org-1", q)
    assert "org-1" not in broker._subscribers
