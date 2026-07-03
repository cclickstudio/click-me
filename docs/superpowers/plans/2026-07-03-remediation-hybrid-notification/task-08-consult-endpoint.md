# Task 8: consult 엔드포인트 (상담 진입)

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §4
> **실행 규칙**: 백엔드 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 파일 첫 줄 한국어 헤더 주석 · 🅰 소유 파일 수정 금지.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.
> 선행: Task 7 (`_notification_store`·`_publish_org` seam이 이미 있어야 함).

---

**Files:**
- Create: `backend/domain/management/remediation/consult_service.py`
- Modify: `backend/api/routers/management.py` (Task 7 블록에 라우트 1개 추가)
- Test: `test/backend/management/test_notification_consult.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

`test/backend/management/test_notification_consult.py`:

```python
# consult 진입 테스트 — 전이표 전부(스펙 §4): 재클릭/정상화/실패 롤백/CAS 패자/read 동시
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from domain.management.remediation.consult_service import consult_notification


def _consult(status="anomaly"):
    from domain.management.remediation.advisor import build_options
    from domain.management.remediation.contracts import ConsultResult

    return ConsultResult(
        status=status,
        campaign_id="c1",
        campaign_name="여름",
        anomaly_type="no_delivery" if status == "anomaly" else "",
        diagnosed_at=datetime.now(UTC).isoformat(),
        message="상담 ①②",
        options=build_options("no_delivery") if status == "anomaly" else [],
    )


class Store:
    def __init__(self, notif=None, claim=True):
        self.notif = notif or {
            "id": "n1", "organization_id": "org-1", "project_id": "p1",
            "campaign_id": "c1", "kind": "management.remediation_consult",
            "payload": {}, "read_at": None, "resolved_at": None, "resolution": None,
            "consult_session_id": None,
        }
        self._claim = claim
        self.reads, self.resolves, self.releases = [], [], []

    async def get(self, nid):
        return self.notif if nid == self.notif["id"] else None

    async def mark_read(self, org_id, ids, now):
        self.reads.append(ids)
        return len(ids)

    async def resolve(self, org_id, nid, resolution, now):
        self.resolves.append((nid, resolution))
        return True

    async def claim_consult_session(self, nid, sid):
        return self._claim

    async def release_consult_session(self, nid, sid):
        self.releases.append((nid, sid))


class ChatStore:
    def __init__(self, fail_append=False, session_alive=True):
        self.fail_append = fail_append
        self.session_alive = session_alive
        self.appended = []

    async def find_or_create_session(self, project_id, title):
        return "sess-1", None

    async def session_exists(self, session_id):
        return self.session_alive

    async def append_consult(self, session_id, content, meta):
        if self.fail_append:
            raise RuntimeError("append 실패")
        self.appended.append((session_id, meta))


class _Settings:
    pass


def _run(store, chat_store, *, consult_result="anomaly", published=None):
    async def _consult_fn(settings, campaign_id, **kw):
        return None if consult_result == "fail" else _consult(status=consult_result)

    return consult_notification(
        _Settings(), "n1", "org-1",
        store=store, chat_store=chat_store, consult=_consult_fn,
        publish=(published.append if published is not None else lambda _o: None),
        now=lambda: datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_happy_path_seeds_session_and_marks_read():
    store, chat, published = Store(), ChatStore(), []
    out = await _run(store, chat, published=published)
    assert out == {"status": "consult", "session_id": "sess-1"}
    assert chat.appended and chat.appended[0][1]["kind"] == "remediation_consult"
    assert store.reads == [["n1"]]  # 상담 클릭 = read 동시 처리
    assert published == ["org-1"]


@pytest.mark.asyncio
async def test_wrong_org_returns_none():
    n = {"id": "n1", "organization_id": "org-2", "project_id": "p1", "campaign_id": "c1",
         "kind": "k", "payload": {}, "read_at": None, "resolved_at": None,
         "resolution": None, "consult_session_id": None}
    out = await _run(Store(notif=n), ChatStore())
    assert out is None  # 라우터가 404로 변환


@pytest.mark.asyncio
async def test_already_resolved_returns_gentle_status():
    n = Store().notif | {"resolved_at": datetime.now(UTC), "resolution": "ignored"}
    out = await _run(Store(notif=n), ChatStore())
    assert out == {"status": "already_resolved", "resolution": "ignored"}


@pytest.mark.asyncio
async def test_reclick_navigates_without_reverify():
    calls = []

    async def counting_consult(settings, campaign_id, **kw):
        calls.append(1)
        return _consult()

    n = Store().notif | {"consult_session_id": "sess-9", "read_at": datetime.now(UTC)}
    store, chat = Store(notif=n), ChatStore()
    out = await consult_notification(
        _Settings(), "n1", "org-1", store=store, chat_store=chat,
        consult=counting_consult, publish=lambda _o: None,
        now=lambda: datetime.now(UTC),
    )
    assert out == {"status": "consult", "session_id": "sess-9"}
    assert calls == []  # 재클릭 = 이동 전용(스펙 §4 결정)


@pytest.mark.asyncio
async def test_deleted_session_restarts_flow():
    n = Store().notif | {"consult_session_id": "sess-9"}
    store, chat = Store(notif=n), ChatStore(session_alive=False)
    out = await _run(store, chat)
    assert out == {"status": "consult", "session_id": "sess-1"}  # 새로 심었다
    assert chat.appended


@pytest.mark.asyncio
async def test_normalized_resolves_auto_normal():
    store, published = Store(), []
    out = await _run(store, ChatStore(), consult_result="normal", published=published)
    assert out["status"] == "normal"
    assert store.resolves == [("n1", "auto_normal")]
    assert published == ["org-1"]


@pytest.mark.asyncio
async def test_consult_failure_returns_retryable():
    out = await _run(Store(), ChatStore(), consult_result="fail")
    assert out == {"status": "unavailable"}  # 라우터가 503으로 변환


@pytest.mark.asyncio
async def test_append_failure_rolls_back_cas():
    store, chat = Store(), ChatStore(fail_append=True)
    out = await _run(store, chat)
    assert out == {"status": "unavailable"}
    assert store.releases == [("n1", "sess-1")]  # 보상 롤백 — 빈 세션 영구 안내 방지


@pytest.mark.asyncio
async def test_cas_loser_returns_same_session_without_append():
    store, chat = Store(claim=False), ChatStore()
    out = await _run(store, chat)
    assert out == {"status": "consult", "session_id": "sess-1"}  # 승자 미확정 시 폴백
    assert chat.appended == []  # 패자는 심지 않는다


@pytest.mark.asyncio
async def test_cas_loser_follows_winner_session():
    """패자는 재조회로 승자가 확정한 세션을 반환한다 — find_or_create race 대비."""
    store, chat = Store(claim=False), ChatStore()
    calls = {"n": 0}
    orig_get = store.get

    async def get(nid):
        calls["n"] += 1
        if calls["n"] == 1:  # 최초 조회 — 아직 미확정
            return await orig_get(nid)
        return store.notif | {"consult_session_id": "sess-winner"}  # 패배 후 재조회 — 승자 확정

    store.get = get
    out = await _run(store, chat)
    assert out == {"status": "consult", "session_id": "sess-winner"}
    assert chat.appended == []
```

- [ ] **Step 2: 실패 확인**

```bash
cd backend && uv run pytest ../test/backend/management/test_notification_consult.py -v
```
Expected: FAIL (`consult_service` 모듈 없음)

- [ ] **Step 3: consult_service 구현**

`backend/domain/management/remediation/consult_service.py`:

```python
# [상담하기] 진입 유스케이스 — 재검증 → 세션 심기(CAS·보상 롤백) → 이동 (🅱)
"""스펙 §4 전이표 구현. 라우터는 반환 dict를 HTTP로 변환만 한다.

재클릭은 재검증 없이 이동 전용(결정) — 재검증은 알림 생성↔첫 상담 갭 해소가 목적이고,
재클릭마다 심으면 세션 스팸. 세션 내 최신 확인은 consult_anomaly 챗 도구가 담당.
CAS(조건부 UPDATE)로 이중 심기 방지 — row lock은 외부 I/O(advisor) 동안 행 잠금을
붙드는 안티패턴이라 채택하지 않음.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_SESSION_TITLE = "⚠ 캠페인 이상 알림"  # chat_sink와 동일 — 프로젝트당 전용 세션 재사용


class DbChatStore:
    """세션 확보·심기·생존 확인 — chat_sink.DbConsultStore 재사용 + 생존 확인 추가."""

    def __init__(self) -> None:
        from domain.management.remediation.chat_sink import DbConsultStore  # noqa: PLC0415

        self._inner = DbConsultStore()

    async def find_or_create_session(self, project_id: str, title: str):
        return await self._inner.find_or_create_session(project_id, title)

    async def append_consult(self, session_id: str, content: str, meta: dict) -> None:
        await self._inner.append_consult(session_id, content, meta)

    async def session_exists(self, session_id: str) -> bool:
        from uuid import UUID  # noqa: PLC0415

        from sqlalchemy import select  # noqa: PLC0415

        from core.db import AsyncSessionLocal  # noqa: PLC0415
        from core.models import ChatSession  # noqa: PLC0415

        async with AsyncSessionLocal() as db:
            row = await db.execute(select(ChatSession.id).where(ChatSession.id == UUID(session_id)))
            return row.first() is not None


async def consult_notification(
    settings: Any,
    notification_id: str,
    org_id: str,
    *,
    store: Any,
    chat_store: Any,
    consult: Any,
    publish: Any,
    now: Any = None,
) -> dict | None:
    """전이표(스펙 §4). None=404(타 org·없음) / unavailable=503 / 나머지 200."""
    now = now or (lambda: datetime.now(UTC))
    n = await store.get(notification_id)
    if n is None or n["organization_id"] != org_id:
        return None  # fail-closed — 존재 여부도 노출하지 않는다

    read_changed = False
    if n["read_at"] is None:
        read_changed = bool(await store.mark_read(org_id, [notification_id], now()))

    try:
        if n["resolved_at"] is not None:
            return {"status": "already_resolved", "resolution": n["resolution"]}

        if n["consult_session_id"]:
            if await chat_store.session_exists(n["consult_session_id"]):
                return {"status": "consult", "session_id": n["consult_session_id"]}
            # 사용자가 세션을 지웠다 — CAS를 비우고 처음부터 재실행(스펙 §4 엣지)
            await store.release_consult_session(notification_id, n["consult_session_id"])

        result = await consult(settings, n["campaign_id"])
        if result is None:
            return {"status": "unavailable"}
        if result.status == "normal":
            await store.resolve(org_id, notification_id, "auto_normal", now())
            return {"status": "normal", "message": result.message}

        session_id, _last_read = await chat_store.find_or_create_session(
            n["project_id"], _SESSION_TITLE
        )
        if await store.claim_consult_session(notification_id, session_id):
            meta = result.to_meta(org_id=org_id)
            try:
                await chat_store.append_consult(session_id, result.message, meta)
            except Exception:  # noqa: BLE001 — 심기 실패는 보상 롤백 후 재시도 가능 응답
                await store.release_consult_session(notification_id, session_id)
                return {"status": "unavailable"}
        else:
            # CAS 패자 — find_or_create 자체의 race로 승자와 다른 세션을 쥘 수 있다.
            # 승자가 확정한 세션을 재조회해 그쪽으로 안내(없으면 방금 세션 폴백).
            latest = await store.get(notification_id)
            session_id = (latest or {}).get("consult_session_id") or session_id
        return {"status": "consult", "session_id": session_id}
    finally:
        if read_changed:
            publish(org_id)  # 어느 경로로 끝나든 read 변화는 배지 동기화(스펙 §4 ①)
```

- [ ] **Step 4: 라우트 추가**

`backend/api/routers/management.py` Task 7 블록의 resolve 라우트 아래에:

```python
@router.post("/notifications/{notification_id}/consult")
async def consult_from_notification(
    notification_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """[상담하기] — 재검증 후 전용 세션에 상담 심기, session_id 반환(스펙 §4 전이표)."""
    from domain.management.remediation import advisor  # noqa: PLC0415
    from domain.management.remediation.consult_service import (  # noqa: PLC0415
        DbChatStore,
        consult_notification,
    )

    org_id = str(await _require_org_id(user, db))
    out = await consult_notification(
        settings, notification_id, org_id,
        store=_notification_store(), chat_store=DbChatStore(),
        consult=advisor.consult, publish=_publish_org,
    )
    if out is None:
        raise HTTPException(404, "알림을 찾을 수 없습니다.")
    if out["status"] == "unavailable":
        raise HTTPException(503, "지금은 상담을 준비할 수 없어요. 잠시 후 다시 시도해 주세요.")
    if out["status"] in ("consult", "normal"):
        _publish_org(org_id)  # 상태 변화(세션 연결·auto_normal) 배지 동기화
    return out
```

- [ ] **Step 5: 통과 확인 + Ruff + 커밋**

```bash
cd backend && uv run pytest ../test/backend/management/test_notification_consult.py -v
cd backend && uv run ruff format . && uv run ruff check . --fix && cd ..
git add backend/domain/management/remediation/consult_service.py backend/api/routers/management.py test/backend/management/test_notification_consult.py
git commit -m "add: [상담하기] consult 엔드포인트 — 재검증·CAS 심기·보상 롤백·전이표"
```
