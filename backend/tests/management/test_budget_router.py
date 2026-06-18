# 예산 관리 라우터 — /budget · /budget/limit (한도 대비 캠페인 합산 소진 + 90/95/100% 판정)
"""캠페인 지출 합산 소진과 한도 설정에 따른 BudgetDecision 전환을 확인한다."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management

_DECISIONS = {"allow", "warn", "escalate", "block"}


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
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
