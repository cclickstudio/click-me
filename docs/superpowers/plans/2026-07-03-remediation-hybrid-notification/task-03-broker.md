# Task 3: SSE 인프로세스 브로커

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §5
> **실행 규칙**: 백엔드 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 파일 첫 줄 한국어 헤더 주석 · 🅰 소유 파일 수정 금지.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Create: `backend/domain/management/remediation/broker.py`
- Test: `test/backend/management/test_notification_broker.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

`test/backend/management/test_notification_broker.py`:

```python
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
```

- [ ] **Step 2: 실패 확인**

```bash
cd backend && uv run pytest ../test/backend/management/test_notification_broker.py -v
```
Expected: FAIL (`broker` 모듈 없음)

- [ ] **Step 3: 구현**

`backend/domain/management/remediation/broker.py`:

```python
# 알림 SSE 인프로세스 브로커 — org별 "changed" 신호 pub/sub (🅱)
"""단일 프로세스 전제(단일 EC2·인프로세스 async 아키텍처 결정). 멀티워커 배포 시
management_notify_sse_enabled=false로 끄면 프론트가 폴링 폴백으로 동작한다.

이벤트는 내용 없는 "changed" 신호뿐 — 수신 측은 목록 refetch만 한다. 큐가 가득하면
새 신호를 드랍해도 무손실: 미소비 신호가 이미 있고, 구독자는 깨어나면 refetch 1회로 병합.
"""

from __future__ import annotations

import asyncio

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
        try:
            q.put_nowait("changed")
        except asyncio.QueueFull:
            pass  # 드랍 — 문서 최상단 근거 참조
```

- [ ] **Step 4: 통과 확인 + Ruff + 커밋**

```bash
cd backend && uv run pytest ../test/backend/management/test_notification_broker.py -v
cd backend && uv run ruff format . && uv run ruff check . --fix && cd ..
git add backend/domain/management/remediation/broker.py test/backend/management/test_notification_broker.py
git commit -m "add: 알림 SSE 인프로세스 브로커 — org별 changed 신호 pub/sub"
```
