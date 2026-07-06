# 예산 관리 라우터 — /budget · /budget/limit (한도 대비 캠페인 합산 소진 + 90/95/100% 판정)
"""캠페인 지출 합산 소진과 한도 설정에 따른 BudgetDecision 전환을 확인한다."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from core.auth import get_current_user
from core.db import get_db

_DECISIONS = {"allow", "warn", "escalate", "block"}


class _FakeDB:
    """/budget/limit 인증용 가짜 DB — organization_members 조회 시 org_id를 반환."""

    def __init__(self, org_id):
        self._org_id = org_id

    async def scalar(self, stmt, *a, **k):
        if "organization_members" in str(stmt):
            return self._org_id
        return None


@pytest.fixture(autouse=True)
def _restore_budget_limit():
    """인메모리 _BUDGET 한도 원복 — set_limit 잔류가 다른 테스트(executor 판정)로 새지 않게."""
    before = management._BUDGET.for_tenant(management.TENANT_ID).limit_krw
    yield
    management._BUDGET.set_limit(management.TENANT_ID, before)


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    org_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: _FakeDB(org_id=org_id)
    return TestClient(app)


def test_budget_has_summary_and_decision(client):
    b = client.get("/api/management/budget").json()
    keys = ("limit_krw", "spent_krw", "remaining_krw", "ratio", "decision", "thresholds")
    for key in (*keys, "campaigns"):
        assert key in b
    assert b["spent_krw"] > 0  # 데모 캠페인 지출 합산
    assert b["decision"] in _DECISIONS
    assert len(b["campaigns"]) == 5
    assert b["thresholds"] == {"warn": 0.90, "escalate": 0.95}


def test_set_limit_drives_decision(client):
    spent = client.get("/api/management/budget").json()["spent_krw"]

    # 한도 < 소진 → 초과 차단
    over = client.post("/api/management/budget/limit", json={"limit_krw": spent // 2}).json()
    assert over["decision"] == "block"
    assert over["ratio"] > 1.0

    # 한도 충분 → 정상
    ok = client.post("/api/management/budget/limit", json={"limit_krw": spent * 10}).json()
    assert ok["decision"] == "allow"
    assert ok["remaining_krw"] == spent * 10 - spent


def test_set_limit_rejects_negative(client):
    res = client.post("/api/management/budget/limit", json={"limit_krw": -1})
    assert res.status_code == 422  # limit_krw ge=0
