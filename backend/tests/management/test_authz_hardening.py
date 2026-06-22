# 🅱 매니지먼트 인증·소유권 강화(Vuln 3) — 헬퍼 단위 + 엔드포인트 인증/소유권
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routers import management
from core.auth import get_current_user
from core.db import get_db


class _FakeScalars:
    def __init__(self, v):
        self._v = v

    def first(self):
        return self._v

    def all(self):
        return [self._v] if self._v is not None else []


class _FakeResult:
    def __init__(self, v):
        self._v = v

    def scalars(self):
        return _FakeScalars(self._v)


class _FakeDB:
    """db.scalar는 쿼리 대상 테이블로 분기, db.execute는 캠페인 행을 반환."""

    def __init__(self, *, org_id=None, conn=None, campaign=None):
        self._org_id = org_id
        self._conn = conn
        self._campaign = campaign

    async def scalar(self, stmt, *a, **k):
        s = str(stmt)
        if "organization_members" in s:
            return self._org_id
        if "meta_connections" in s:
            return self._conn
        return None

    async def execute(self, stmt, *a, **k):
        return _FakeResult(self._campaign)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def delete(self, obj):
        pass


@pytest.mark.asyncio
async def test_require_org_id_raises_409_without_org():
    db = _FakeDB(org_id=None)
    with pytest.raises(HTTPException) as exc:
        await management._require_org_id(SimpleNamespace(id=uuid.uuid4()), db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_require_owned_campaign_cross_tenant_403():
    org = uuid.uuid4()
    other = uuid.uuid4()
    db = _FakeDB(campaign=SimpleNamespace(tenant_id=str(other), daily_budget_krw=1000, name="x"))
    with pytest.raises(HTTPException) as exc:
        await management._require_owned_campaign(db, org, "camp_x")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_owned_campaign_owned_returns_row():
    org = uuid.uuid4()
    db = _FakeDB(campaign=SimpleNamespace(tenant_id=str(org), daily_budget_krw=1000, name="x"))
    row = await management._require_owned_campaign(db, org, "camp_x")
    assert row.tenant_id == str(org)


@pytest.mark.asyncio
async def test_require_owned_campaign_unknown_404(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", True, raising=False)
    db = _FakeDB(campaign=None)
    with pytest.raises(HTTPException) as exc:
        await management._require_owned_campaign(db, uuid.uuid4(), "totally_unknown")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_require_owned_campaign_demo_fixture_allows_none(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", True, raising=False)
    db = _FakeDB(campaign=None)
    demo_id = management._CAMPAIGNS_DEMO[0][0]
    assert await management._require_owned_campaign(db, uuid.uuid4(), demo_id) is None


@pytest.mark.asyncio
async def test_require_ad_account_live_failclosed_without_connection(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", False, raising=False)
    db = _FakeDB(conn=None)
    with pytest.raises(HTTPException) as exc:
        await management._require_ad_account(db, uuid.uuid4())
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_require_ad_account_mock_falls_back_to_demo(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", True, raising=False)
    db = _FakeDB(conn=None)
    assert await management._require_ad_account(db, uuid.uuid4()) == management._DEMO_AD_ACCOUNT


@pytest.mark.asyncio
async def test_escalation_controller_get_run_reads_store():
    from domain.management.escalation import EscalationController, EscalationRun

    run = EscalationRun(
        tenant_id="org_1",
        ad_account_id="act_1",
        campaign_id="camp_1",
        anomaly_type="quality_degraded",
        ladder=["REPLACE_CREATIVE", "CREATE_CAMPAIGN"],
    )

    class _Store:
        async def get_by_run_id(self, run_id):
            return run if run_id == run.run_id else None

    ctrl = EscalationController(store=_Store(), detector=object(), agent=object(), audit=object())
    assert (await ctrl.get_run(run.run_id)) is run
    assert (await ctrl.get_run("nope")) is None


def _client_no_auth():
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    return TestClient(app, raise_server_exceptions=False)


def test_execute_requires_auth():
    res = _client_no_auth().post("/api/management/execute", json={})
    assert res.status_code == 401


def test_regenerate_requires_auth():
    res = _client_no_auth().post("/api/management/regenerate", json={})
    assert res.status_code == 401


def test_create_proposal_requires_auth():
    res = _client_no_auth().post("/api/management/campaigns/create-proposal", json={})
    assert res.status_code == 401


def test_from_candidate_requires_auth():
    res = _client_no_auth().post("/api/management/campaign-proposals/from-candidate", json={})
    assert res.status_code == 401


def test_ad_image_requires_auth():
    res = _client_no_auth().post("/api/management/ad-image")
    assert res.status_code == 401


def _client_with(org_id, *, campaign=None, conn=None, use_mock=True, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(management.settings, "use_mock", use_mock, raising=False)
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: _FakeDB(org_id=org_id, campaign=campaign, conn=conn)
    return TestClient(app, raise_server_exceptions=False)


def test_delete_requires_auth():
    res = _client_no_auth().delete("/api/management/campaigns/camp_x")
    assert res.status_code == 401


def test_sync_requires_auth():
    res = _client_no_auth().get("/api/management/campaigns/camp_x/sync")
    assert res.status_code == 401


def test_delete_cross_tenant_403(monkeypatch):
    org = uuid.uuid4()
    other = uuid.uuid4()
    campaign = SimpleNamespace(tenant_id=str(other), daily_budget_krw=1000, name="x")
    client = _client_with(org, campaign=campaign, monkeypatch=monkeypatch)
    res = client.delete("/api/management/campaigns/camp_x")
    assert res.status_code == 403


def test_sync_unknown_campaign_404(monkeypatch):
    org = uuid.uuid4()
    client = _client_with(org, campaign=None, use_mock=True, monkeypatch=monkeypatch)
    res = client.get("/api/management/campaigns/totally_unknown/sync")
    assert res.status_code == 404


def test_budget_limit_requires_auth():
    res = _client_no_auth().post("/api/management/budget/limit", json={"limit_krw": 1000})
    assert res.status_code == 401


def _async_return(value):
    async def _coro(*a, **k):
        return value

    return _coro()


def test_re_evaluate_requires_auth():
    res = _client_no_auth().post("/api/management/re-evaluate", json={})
    assert res.status_code == 401


def test_rung_executed_cross_tenant_403(monkeypatch):
    org = uuid.uuid4()
    other = uuid.uuid4()
    run = SimpleNamespace(tenant_id=str(other), run_id="esc_1")
    monkeypatch.setattr(
        management,
        "_get_escalation",
        lambda: SimpleNamespace(get_run=lambda rid: _async_return(run)),
    )
    client = _client_with(org, monkeypatch=monkeypatch)
    res = client.post("/api/management/re-evaluate/executed", json={"run_id": "esc_1"})
    assert res.status_code == 403
