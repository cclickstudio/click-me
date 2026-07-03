# 알림 SSE 인프로세스 브로커 — org별 "changed" 신호 pub/sub (🅱)
"""단일 프로세스 전제(단일 EC2·인프로세스 async 아키텍처 결정). 멀티워커 배포 시
management_notify_sse_enabled=false로 끄면 프론트가 폴링 폴백으로 동작한다.

이벤트는 내용 없는 "changed" 신호뿐 — 수신 측은 목록 refetch만 한다. 큐가 가득하면
새 신호를 드랍해도 무손실: 미소비 신호가 이미 있고, 구독자는 깨어나면 refetch 1회로 병합.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress

_QUEUE_SIZE = 8

_subscribers: dict[str, set[asyncio.Queue]] = {}


def subscribe(org_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_SIZE)
    _subscribers.setdefault(org_id, set()).add(q)
    return q


def unsubscribe(org_id: str, q: asyncio.Queue) -> None:
    subs = _subscribers.get(org_id)
    if subs is None:
        return
    subs.discard(q)
    if not subs:
        del _subscribers[org_id]


def publish(org_id: str) -> None:
    for q in _subscribers.get(org_id, ()):
        with suppress(asyncio.QueueFull):
            q.put_nowait("changed")  # 드랍 — 문서 최상단 근거 참조
