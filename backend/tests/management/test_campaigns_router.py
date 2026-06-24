# 캠페인 목록·성과 대시보드 라우터 — /campaigns · /campaigns/{id} 왕복 (Mock 데모)
"""데모 캠페인 목록 요약과 캠페인 상세(시간별 노출·기대곡선·요약)가 정상 산출되는지 확인한다."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management

_STATES = {"draft", "under_review", "active", "active_pending_review", "paused", "ended"}


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    return TestClient(app)


def test_list_campaigns_returns_summaries(client):
    res = client.get("/api/management/campaigns")
    assert res.status_code == 200
    campaigns = res.json()["campaigns"]
    assert len(campaigns) == 5
    for c in campaigns:
        assert c["name"]
        assert c["state"] in _STATES
        assert c["daily_budget_krw"] > 0
        # 요약 KPI 존재 + 소진율은 0 이상
        for key in ("impressions", "reach", "spend_krw", "ctr", "cpc_krw", "pacing_pct"):
            assert key in c
        assert c["pacing_pct"] >= 0.0


def test_campaign_detail_has_timeseries(client):
    res = client.get("/api/management/campaigns/camp_1")
    assert res.status_code == 200
    body = res.json()
    assert body["campaign_id"] == "camp_1"
    assert len(body["expected"]) == 24
    assert len(body["actual"]) == 24
    assert "summary" in body
    assert isinstance(body["anomaly_hours"], list)


def test_campaign_detail_unknown_id_404(client):
    res = client.get("/api/management/campaigns/nope")
    assert res.status_code == 404


def test_campaign_outcome_exposes_real_outcome(client):
    res = client.get("/api/management/campaigns/camp_1/outcome")
    assert res.status_code == 200
    body = res.json()
    assert body["campaign_id"] == "camp_1"
    assert body["creative_id"] is None  # 미연결 — 생성→집행 경로가 stamp
    # 전환 추적 전이면 합성 금지 → None
    assert body["conversions"] is None
    assert body["cvr"] is None
    for key in ("impressions", "reach", "spend_krw", "ctr", "cpc_krw", "cpm_krw", "as_of"):
        assert key in body


def test_campaign_outcome_stamps_creative_id(client):
    res = client.get("/api/management/campaigns/camp_1/outcome?creative_id=cre_9")
    assert res.status_code == 200
    assert res.json()["creative_id"] == "cre_9"
