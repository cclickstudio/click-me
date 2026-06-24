# 오가닉↔광고 비교 라우터 — /compare · /compare/board 왕복 (Mock 데모 경로)
"""ComparisonService가 MockAdPlatform.get_metrics 부재를 인라우터 어댑터로 우회하는지,
LiftResult 형태·verdict가 정상 산출되는지 확인한다."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management

_VERDICTS = {"pass", "caution", "fail"}
_ACTIONS = {"scale_up", "hold", "pause"}


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    return TestClient(app)


def test_compare_one_returns_lift_and_recommendation(client):
    res = client.get("/api/management/compare", params={"post_id": "ig_x", "campaign_id": "camp_x"})
    assert res.status_code == 200
    body = res.json()
    lift = body["lift"]
    rec = body["recommendation"]
    assert lift["verdict"] in _VERDICTS
    assert rec["recommended_action"] in _ACTIONS
    # 묶음 일관성: 권고가 같은 리프트에서 파생
    assert rec["verdict"] == lift["verdict"]
    assert rec["reach_lift_ratio"] == lift["reach_lift_ratio"]


def test_compare_board_returns_rows(client):
    res = client.get("/api/management/compare/board")
    assert res.status_code == 200
    rows = res.json()["rows"]
    assert len(rows) == 4
    for row in rows:
        assert row["title"]
        lift = row["lift"]
        assert lift["organic"]["post_type"] == "organic"
        assert lift["paid"]["post_type"] == "paid"
        assert lift["verdict"] in _VERDICTS
        # 증분 = 광고 도달 - 오가닉 도달, 오가닉은 비용·클릭 0
        assert lift["reach_lift_abs"] == lift["paid"]["reach"] - lift["organic"]["reach"]
        assert lift["organic"]["spend_krw"] == 0
        assert lift["organic"]["clicks"] == 0
        # 행마다 권고가 함께 (verdict와 일관)
        rec = row["recommendation"]
        assert rec["recommended_action"] in _ACTIONS
        assert rec["verdict"] == lift["verdict"]


def test_board_budget_spread_lowers_ratio(client):
    """큰 예산 행이 작은 예산 행보다 증분 배수가 높다(도달 스프레드 의도 확인)."""
    rows = client.get("/api/management/compare/board").json()["rows"]
    first_ratio = rows[0]["lift"]["reach_lift_ratio"]  # 200,000원
    last_ratio = rows[-1]["lift"]["reach_lift_ratio"]  # 15,000원
    assert first_ratio > last_ratio
