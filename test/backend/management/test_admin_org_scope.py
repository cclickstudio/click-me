# admin org 스코프 — 헤더 캡처·해석기·검증·전역뷰 테스트
import uuid
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from core.auth import get_current_user
from core.db import get_db


@pytest.fixture(autouse=True)
def _reset_org_ctx():
    """각 테스트 전후로 ContextVar 초기화 — 요청 밖 누수/순서 의존 제거."""
    token = management._selected_org_ctx.set(None)
    yield
    management._selected_org_ctx.reset(token)


def test_header_captured_during_and_reset_after():
    """요청 중 헤더를 ContextVar에 캡처하고 요청 후 reset 하는지 (로컬 router로 전역 오염 방지)."""
    seen = {}
    probe = APIRouter(dependencies=[Depends(management._capture_selected_org)])

    @probe.get("/__ctxprobe")
    async def _p():
        seen["during"] = management._selected_org_ctx.get()
        return {"ok": True}

    app = FastAPI()
    app.include_router(probe)
    TestClient(app).get("/__ctxprobe", headers={"X-Org-Id": "org-abc"})
    assert seen["during"] == "org-abc"
    assert management._selected_org_ctx.get() is None  # 요청 후 reset


class _OrgDB:
    """Organization.status 조회만 흉내내는 최소 FakeDB."""

    def __init__(self, status):
        self._status = status

    async def scalar(self, *_a, **_k):
        return self._status


@pytest.mark.asyncio
async def test_validated_org_bad_uuid_400():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        await management._validated_org(_OrgDB("ACTIVE"), "not-a-uuid", require_active=True)
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_validated_org_missing_404():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        await management._validated_org(_OrgDB(None), str(uuid.uuid4()), require_active=True)
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_validated_org_inactive_blocked_for_operational_409():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        await management._validated_org(_OrgDB("SUSPENDED"), str(uuid.uuid4()), require_active=True)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_validated_org_inactive_allowed_for_read():
    org = uuid.uuid4()
    got = await management._validated_org(_OrgDB("SUSPENDED"), str(org), require_active=False)
    assert got == org


class _MembershipDB:
    """require_user_org 경로 — 멤버십 org 반환."""

    def __init__(self, org):
        self._org = org

    async def scalar(self, *_a, **_k):
        return self._org


@pytest.mark.asyncio
async def test_non_admin_ignores_header_uses_own_org():
    """IDOR 회귀 — 비-ADMIN이 X-Org-Id 보내도 무시하고 자기 org."""
    own = uuid.uuid4()
    management._selected_org_ctx.set(str(uuid.uuid4()))  # 남의 org 힌트
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    assert await management._require_org_id(user, _MembershipDB(own)) == own


@pytest.mark.asyncio
async def test_admin_without_header_400():
    from fastapi import HTTPException

    user = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    with pytest.raises(HTTPException) as e:
        await management._require_org_id(user, _OrgDB("ACTIVE"))
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_admin_with_header_uses_selected_org():
    sel = uuid.uuid4()
    management._selected_org_ctx.set(str(sel))
    user = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    assert await management._require_org_id(user, _OrgDB("ACTIVE")) == sel


def _client(user, db):
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_admin_cannot_impersonate_meta_connect(monkeypatch):
    """org 소유자 액션(Meta 연결)은 admin 대리 불가 → 409."""
    # meta_app_id가 없으면 flow가 org 체크 전에 503으로 끊긴다 → org 체크(409)에 도달하도록 설정.
    monkeypatch.setattr(management.settings, "meta_app_id", "test_app", raising=False)
    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")

    class _DB:
        async def scalar(self, *_a, **_k):
            return None  # admin은 멤버십 없음

    res = _client(admin, _DB()).get(
        "/api/management/meta/connect", headers={"X-Org-Id": str(uuid.uuid4())}
    )
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_emit_impersonation_audit_records(monkeypatch):
    captured = []

    class _Sink:
        async def append(self, event):
            captured.append(event)

    monkeypatch.setattr(management, "_AUDIT_LOG", _Sink())
    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    org = uuid.uuid4()
    await management._emit_impersonation_audit(admin, org, action="approve")
    assert len(captured) == 1
    ev = captured[0]
    assert ev.category == "impersonation"
    assert ev.tenant_id == str(org)
    assert ev.payload["actor"] == str(admin.id)
    assert ev.payload["action"] == "approve"
    assert ev.payload["outcome"] == "attempted"


@pytest.mark.asyncio
async def test_emit_impersonation_audit_noop_for_non_admin(monkeypatch):
    captured = []

    class _Sink:
        async def append(self, event):
            captured.append(event)

    monkeypatch.setattr(management, "_AUDIT_LOG", _Sink())
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    await management._emit_impersonation_audit(user, uuid.uuid4(), action="approve")
    assert captured == []


@pytest.mark.asyncio
async def test_require_org_id_write_resolves_and_emits(monkeypatch):
    calls = []

    async def _spy(user, org_id, *, action):
        calls.append((str(org_id), action))

    monkeypatch.setattr(management, "_emit_impersonation_audit", _spy)
    sel = uuid.uuid4()
    management._selected_org_ctx.set(str(sel))
    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    got = await management._require_org_id_write(admin, _OrgDB("ACTIVE"), action="approve")
    assert got == sel
    assert calls == [(str(sel), "approve")]


@pytest.mark.asyncio
async def test_require_org_id_write_non_admin_returns_org(monkeypatch):
    async def _spy(*_a, **_k):
        return None

    monkeypatch.setattr(management, "_emit_impersonation_audit", _spy)
    own = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    got = await management._require_org_id_write(user, _MembershipDB(own), action="approve")
    assert got == own


def test_sync_campaign_admin_charge_emits_targeted_audit(monkeypatch):
    """admin이 X-Org-Id로 sync해서 실제 크레딧 차감이 나면 sync_credit_adjust 감사 1건."""
    emitted = []

    async def _spy(user, org_id, *, action):
        emitted.append((str(org_id), action))

    org = uuid.uuid4()

    async def _fake_require_org_id(user, db):
        return org

    class _Reader:
        async def get_metrics(self, *_a, **_k):
            return SimpleNamespace(spend_krw=10_000, as_of=None)

        async def get_delivery_status_detail(self, *_a, **_k):
            return SimpleNamespace(effective_status="ACTIVE")

    class _Billing:
        async def spent_for(self, *_a, **_k):
            return 0

        async def balance(self, *_a, **_k):
            return 100_000

        async def record_spend(self, *_a, **_k):
            return None

    async def _noop(*_a, **_k):
        return None

    async def _reader(*_a, **_k):
        return _Reader()

    monkeypatch.setattr(management, "_emit_impersonation_audit", _spy)
    monkeypatch.setattr(management, "_require_org_id", _fake_require_org_id)
    monkeypatch.setattr(management, "_require_owned_campaign", _noop)
    monkeypatch.setattr(management, "_require_reader", _reader)
    monkeypatch.setattr(management, "get_billing_service", lambda: _Billing())
    monkeypatch.setattr(management, "_created_campaign_row", _noop)

    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")

    class _DB:
        async def scalar(self, *_a, **_k):
            return "ACTIVE"

    res = _client(admin, _DB()).get(
        "/api/management/campaigns/camp_x/sync", headers={"X-Org-Id": str(org)}
    )
    assert res.status_code == 200
    assert emitted == [(str(org), "sync_credit_adjust")]


def test_sync_campaign_no_charge_no_audit(monkeypatch):
    """차감이 0이면(이미 정산됨) 감사 없음."""
    emitted = []

    async def _spy(user, org_id, *, action):
        emitted.append(action)

    org = uuid.uuid4()

    async def _fake_require_org_id(user, db):
        return org

    class _Reader:
        async def get_metrics(self, *_a, **_k):
            return SimpleNamespace(spend_krw=5_000, as_of=None)

        async def get_delivery_status_detail(self, *_a, **_k):
            return SimpleNamespace(effective_status="ACTIVE")

    class _Billing:
        async def spent_for(self, *_a, **_k):
            return 5_000  # already == spent → delta 0 → no charge

        async def balance(self, *_a, **_k):
            return 100_000

        async def record_spend(self, *_a, **_k):
            return None

    async def _noop(*_a, **_k):
        return None

    async def _reader(*_a, **_k):
        return _Reader()

    monkeypatch.setattr(management, "_emit_impersonation_audit", _spy)
    monkeypatch.setattr(management, "_require_org_id", _fake_require_org_id)
    monkeypatch.setattr(management, "_require_owned_campaign", _noop)
    monkeypatch.setattr(management, "_require_reader", _reader)
    monkeypatch.setattr(management, "get_billing_service", lambda: _Billing())
    monkeypatch.setattr(management, "_created_campaign_row", _noop)

    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")

    class _DB:
        async def scalar(self, *_a, **_k):
            return "ACTIVE"

    res = _client(admin, _DB()).get(
        "/api/management/campaigns/camp_x/sync", headers={"X-Org-Id": str(org)}
    )
    assert res.status_code == 200
    assert emitted == []
