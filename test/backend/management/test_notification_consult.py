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


async def _ctx_alive(_session_id):
    return True


async def _ctx_dead(_session_id):
    return False


def _run(store, chat_store, *, consult_result="anomaly", published=None, context_alive=None):
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
        context_alive=context_alive,
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
async def test_reclick_with_live_context_navigates_without_reverify():
    """옵션이 아직 진행 가능한 세션이면 재클릭 = 이동 전용(스펙 §4 결정 유지)."""
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
        context_alive=_ctx_alive,
    )
    assert out == {"status": "consult", "session_id": "sess-9"}
    assert calls == []  # 컨텍스트 살아있음 = 이동 전용
    assert chat.appended == []


@pytest.mark.asyncio
async def test_reclick_reseeds_same_session_when_context_dead():
    """옵션 진행됨/만료된 세션 재진입 — 재검증 후 같은 세션에 상담 카드를 다시 심는다.

    회귀 방지: 진행 잔재(조치 확인 카드)만 남은 세션으로 이동해 '선택지 없이 ③이 바로 뜨는'
    증상(2026-07-06 보고)을 재심기로 해소한다.
    """
    n = Store().notif | {"consult_session_id": "sess-9", "read_at": datetime.now(UTC)}
    store, chat, published = Store(notif=n), ChatStore(), []
    out = await _run(store, chat, published=published, context_alive=_ctx_dead)
    assert out == {"status": "consult", "session_id": "sess-9"}
    assert chat.appended and chat.appended[0][0] == "sess-9"  # 같은 세션에 재심기
    assert chat.appended[0][1]["kind"] == "remediation_consult"
    assert published == ["org-1"]  # 재심기 = 상태 변화 → 배지 동기화


@pytest.mark.asyncio
async def test_reclick_reseed_normal_resolves_auto_normal():
    """재심기 재검증에서 정상이면 알림을 auto_normal로 해소한다(신규 경로와 동일 판정)."""
    n = Store().notif | {"consult_session_id": "sess-9", "read_at": datetime.now(UTC)}
    store, chat = Store(notif=n), ChatStore()
    out = await _run(store, chat, consult_result="normal", context_alive=_ctx_dead)
    assert out["status"] == "normal"
    assert store.resolves == [("n1", "auto_normal")]
    assert chat.appended == []


@pytest.mark.asyncio
async def test_reclick_reseed_consult_failure_returns_retryable():
    n = Store().notif | {"consult_session_id": "sess-9", "read_at": datetime.now(UTC)}
    out = await _run(Store(notif=n), ChatStore(), consult_result="fail", context_alive=_ctx_dead)
    assert out == {"status": "unavailable"}


@pytest.mark.asyncio
async def test_reclick_reseed_append_failure_keeps_session_link():
    """재심기 append 실패는 재시도 가능(503)으로 끝내되, 기존 세션 연결은 유지한다."""
    n = Store().notif | {"consult_session_id": "sess-9", "read_at": datetime.now(UTC)}
    store, chat = Store(notif=n), ChatStore(fail_append=True)
    out = await _run(store, chat, context_alive=_ctx_dead)
    assert out == {"status": "unavailable"}
    assert store.releases == []  # 세션은 살아있다 — CAS 롤백 대상 아님


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
async def test_already_read_normal_still_publishes():
    """read 변화가 없어도 상태 변화(auto_normal)면 배지 신호가 나간다 — 발행 책임 일원화."""
    n = Store().notif | {"read_at": datetime.now(UTC)}
    store, published = Store(notif=n), []
    out = await _run(store, ChatStore(), consult_result="normal", published=published)
    assert out["status"] == "normal"
    assert published == ["org-1"]


@pytest.mark.asyncio
async def test_consult_failure_returns_retryable():
    out = await _run(Store(), ChatStore(), consult_result="fail")
    assert out == {"status": "unavailable"}  # 라우터가 503으로 변환


@pytest.mark.asyncio
async def test_consult_raise_returns_retryable():
    """주입 consult가 raise해도 500이 아니라 unavailable(→503) — 계약 미보장 방어."""

    async def raising_consult(settings, campaign_id, **kw):
        raise RuntimeError("reader down")

    out = await consult_notification(
        _Settings(),
        "n1",
        "org-1",
        store=Store(),
        chat_store=ChatStore(),
        consult=raising_consult,
        publish=lambda _o: None,
        now=lambda: datetime.now(UTC),
    )
    assert out == {"status": "unavailable"}


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
