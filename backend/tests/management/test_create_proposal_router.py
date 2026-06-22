# 신규 캠페인 생성 제안 라우터 — /campaigns/create-proposal → /approve → /execute 왕복
"""폼 입력으로 CREATE_CAMPAIGN 제안(Tier 3)을 만들고 승인·실행 경로로 생성(DRY_RUN)되는지 확인."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from domain.management.contracts.schemas import ActionProposal, verify_proposal_hash

_BODY = {"name": "가을 신상 런칭", "daily_budget_krw": 50_000, "run_days": 7}


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
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


def test_create_proposal_rejects_invalid_budget(client):
    res = client.post(
        "/api/management/campaigns/create-proposal",
        json={"name": "x", "daily_budget_krw": 0, "run_days": 7},
    )
    assert res.status_code == 422  # daily_budget_krw ge=1000
