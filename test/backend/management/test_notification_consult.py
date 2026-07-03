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
            "id": "n1",
            "organization_id": "org-1",
            "project_id": "p1",
            "campaign_id": "c1",
            "kind": "management.remediation_consult",
            "payload": {},
            "read_at": None,
            "resolved_at": None,
            "resolution": None,
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
        _Settings(),
        "n1",
        "org-1",
        store=store,
        chat_store=chat_store,
        consult=_consult_fn,
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
    n = {
        "id": "n1",
        "organization_id": "org-2",
        "project_id": "p1",
        "campaign_id": "c1",
        "kind": "k",
        "payload": {},
        "read_at": None,
        "resolved_at": None,
        "resolution": None,
        "consult_session_id": None,
    }
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
        _Settings(),
        "n1",
        "org-1",
        store=store,
        chat_store=chat,
        consult=counting_consult,
        publish=lambda _o: None,
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
