# 신규 캠페인 생성 제안 라우터 — /campaigns/create-proposal → /approve → /execute 왕복
"""폼 입력으로 CREATE_CAMPAIGN 제안(Tier 3)을 만들고 승인·실행 경로로 생성(DRY_RUN)되는지 확인."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from core.auth import get_current_user
from core.db import get_db
from domain.management.contracts.schemas import ActionProposal, verify_proposal_hash

_BODY = {"name": "가을 신상 런칭", "daily_budget_krw": 50_000, "run_days": 7}


class _FakeScalars:
    def __init__(self, v):
        self._v = v

    def first(self):
        return self._v


class _FakeResult:
    def __init__(self, v):
        self._v = v

    def scalars(self):
        return _FakeScalars(self._v)


class _FakeDB:
    """org 조회(db.scalar)만 흉내 — meta_connections는 None으로 mock fallback."""

    def __init__(self, org_id):
        self._org_id = org_id

    async def scalar(self, stmt, *a, **k):
        if "organization_members" in str(stmt):
            return self._org_id
        return None

    async def execute(self, stmt, *a, **k):
        # 소유권 조회(_created_campaign_row) — org 소유 캠페인 행을 반환해 검증 통과.
        return _FakeResult(
            SimpleNamespace(tenant_id=str(self._org_id), daily_budget_krw=50_000, name="x")
        )

    async def commit(self):
        pass

    async def rollback(self):
        pass


class _FakeDBWithSim(_FakeDB):
    """org 조회(organization_members) + simulations 소유 조회 모두 지원."""

    def __init__(self, org_id, *, sim_owned: bool):
        super().__init__(org_id)
        self._sim_owned = sim_owned

    async def scalar(self, stmt, *a, **k):
        s = str(stmt)
        if "organization_members" in s:
            return self._org_id
        if "simulations" in s:
            return 1 if self._sim_owned else None
        return None


@pytest.fixture()
def client():
    org_id = uuid.uuid4()
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=org_id)
    app.dependency_overrides[get_db] = lambda: _FakeDB(org_id)
    return TestClient(app)


@pytest.fixture()
def client_with_sim_owned():
    org_id = uuid.uuid4()
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=org_id)
    app.dependency_overrides[get_db] = lambda: _FakeDBWithSim(org_id, sim_owned=True)
    return TestClient(app)


@pytest.fixture()
def client_with_sim_not_owned():
    org_id = uuid.uuid4()
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=org_id)
    app.dependency_overrides[get_db] = lambda: _FakeDBWithSim(org_id, sim_owned=False)
    return TestClient(app)


def test_create_proposal_is_tier3_with_config(client):
    res = client.post("/api/management/campaigns/create-proposal", json=_BODY)
    assert res.status_code == 200
    prop = res.json()["proposal"]
    assert prop["action_type"] == "CREATE_CAMPAIGN"
    assert prop["action_tier"] == 3
    assert prop["evidence_metrics"]["campaign_config"]["daily_budget_krw"] == 50_000
    assert prop["max_total_spend_krw"] == 50_000 * 7
    # 해시 무결성 — finalize_proposal이 채운 proposal_hash가 전체 필드와 정합
    assert verify_proposal_hash(ActionProposal.model_validate(prop))


def test_create_proposal_round_trip_to_execution(client):
    prop = client.post("/api/management/campaigns/create-proposal", json=_BODY).json()["proposal"]

    appr = client.post("/api/management/approve", json={"proposal": prop, "approved": True}).json()
    assert appr["status"] == "approved"
    action = appr["approved_action"]

    res = client.post(
        "/api/management/execute", json={"approved_action": action, "proposal": prop}
    ).json()["result"]
    assert res["status"] == "success"
    # executor는 멀티타겟 지원이라 writer 결과를 targets[].response로 감싼다.
    target = res["platform_response_snapshot"]["targets"][0]
    assert target["status"] == "success"
    assert target["response"]["operation"] == "create_campaign"
    assert target["response"]["dry_run"] is True  # 기본 DRY_RUN — Meta 미전송


def test_pause_campaign_returns_paused(client):
    # 일시중지 — 제안→승인→실행 단일 경로. MOCK 모드라 DRY_RUN으로 합성 성공.
    res = client.post("/api/management/campaigns/cmp_test_pause/pause")
    assert res.status_code == 200
    body = res.json()
    assert body["paused"] is True
    target = body["result"]["platform_response_snapshot"]["targets"][0]
    assert target["response"]["operation"] == "pause"


def test_pause_success_resolves_campaign_notifications(client, monkeypatch):
    """조치 실행 성공 → 그 캠페인의 미해결 알림을 actioned로 정리 + 배지 동기화(보완 2)."""
    calls: list[tuple[str, str]] = []

    class _FakeNotifStore:
        async def resolve_by_campaign(self, org_id, campaign_id, resolution, now):
            calls.append((campaign_id, resolution))
            return 1

    published: list[str] = []
    monkeypatch.setattr(management, "_notification_store", lambda: _FakeNotifStore())
    monkeypatch.setattr(management, "_publish_org", published.append)

    res = client.post("/api/management/campaigns/cmp_notif_pause/pause")
    assert res.json()["paused"] is True
    assert calls == [("cmp_notif_pause", "actioned")]
    assert published  # 해소 건이 있으면 배지 동기화 신호가 나간다


def test_create_proposal_rejects_invalid_budget(client):
    res = client.post(
        "/api/management/campaigns/create-proposal",
        json={"name": "x", "daily_budget_krw": 0, "run_days": 7},
    )
    assert res.status_code == 422  # daily_budget_krw ge=1000


_VALID_SIM_ID = "22222222-2222-2222-2222-222222222222"


def test_create_proposal_with_owned_simulation_id(client_with_sim_owned):
    """유효한 UUID + org 소유 시뮬 → 200, evidence_metrics에 simulation_id 포함."""
    body = {**_BODY, "simulation_id": _VALID_SIM_ID}
    res = client_with_sim_owned.post("/api/management/campaigns/create-proposal", json=body)
    assert res.status_code == 200, res.text
    evidence = res.json()["proposal"]["evidence_metrics"]
    assert evidence["simulation_id"] == _VALID_SIM_ID


def test_create_proposal_malformed_simulation_id(client_with_sim_owned):
    """형식이 잘못된 simulation_id(UUID 아님) → 422."""
    body = {**_BODY, "simulation_id": "not-a-uuid"}
    res = client_with_sim_owned.post("/api/management/campaigns/create-proposal", json=body)
    assert res.status_code == 422


def test_create_proposal_unowned_simulation_id(client_with_sim_not_owned):
    """다른 org의 시뮬(scalar None 반환) → 422."""
    body = {**_BODY, "simulation_id": _VALID_SIM_ID}
    res = client_with_sim_not_owned.post("/api/management/campaigns/create-proposal", json=body)
    assert res.status_code == 422
