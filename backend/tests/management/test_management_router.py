"""management 라우터 — /run→/regenerate→/approve→/execute→/audit 왕복."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    return TestClient(app)


def test_regenerate_returns_replace_creative_proposal(client):
    run = client.get("/api/management/run?fault=bid_loss").json()
    assert run["diagnosis"] is not None

    res = client.post("/api/management/regenerate", json={"diagnosis": run["diagnosis"]})
    assert res.status_code == 200
    proposal = res.json()["proposal"]
    assert proposal["action_type"] == "REPLACE_CREATIVE"
    assert proposal["evidence_metrics"]["selected_candidate_id"]
    assert len(proposal["evidence_metrics"]["candidates"]) >= 1


def test_full_cycle_run_regenerate_approve_execute(client):
    run = client.get("/api/management/run?fault=bid_loss").json()
    proposal = client.post(
        "/api/management/regenerate", json={"diagnosis": run["diagnosis"]}
    ).json()["proposal"]

    approved = client.post(
        "/api/management/approve",
        json={"proposal": proposal, "approved": True, "approver_id": "user_demo"},
    ).json()
    assert approved["status"] == "approved"
    action = approved["approved_action"]

    res = client.post(
        "/api/management/execute", json={"approved_action": action, "proposal": proposal}
    )
    assert res.status_code == 200
    result = res.json()["result"]
    assert result["status"] in ("success", "pending_review")
    assert result["approval_id"] == action["approval_id"]


def test_audit_lists_events_for_approval(client):
    run = client.get("/api/management/run?fault=bid_loss").json()
    proposal = client.post(
        "/api/management/regenerate", json={"diagnosis": run["diagnosis"]}
    ).json()["proposal"]
    action = client.post(
        "/api/management/approve",
        json={"proposal": proposal, "approved": True, "approver_id": "user_demo"},
    ).json()["approved_action"]
    client.post("/api/management/execute", json={"approved_action": action, "proposal": proposal})

    res = client.get(f"/api/management/audit?approval_id={action['approval_id']}")
    assert res.status_code == 200
    events = res.json()["events"]
    assert any(e["category"] == "executor.completed" for e in events)


def test_re_evaluate_escalation_flow(client):
    """re-evaluate → executed → re-evaluate → recovered (같은 함수, 데모 tick)."""
    body = {
        "tenant_id": "org_demo",
        "ad_account_id": "act_demo_001",
        "campaign_id": "camp_esc_router",  # 고유 캠페인 — 싱글톤 스토어 누수 방지
        "now": "2026-06-12T09:00:00+00:00",
    }

    o0 = client.post("/api/management/re-evaluate", json=body).json()
    assert o0["status"] == "escalated"
    assert o0["proposal"]["action_type"] == "CHANGE_BID_STRATEGY"  # BID_LOSS 사다리 1순위(신규)
    run_id = o0["run_id"]

    client.post("/api/management/re-evaluate/executed", json={"run_id": run_id, "now": body["now"]})
    o1 = client.post("/api/management/re-evaluate", json=body).json()
    assert o1["status"] == "escalated"
    assert o1["proposal"]["action_type"] == "EXPAND_AUDIENCE"  # 미회복 → 다음 단계(신규)

    client.post("/api/management/re-evaluate/executed", json={"run_id": run_id, "now": body["now"]})
    o2 = client.post("/api/management/re-evaluate", json=body).json()
    assert o2["status"] == "recovered"  # 2단계 집행 후 anomaly 소멸


def test_re_evaluate_rejected_shows_notice(client):
    """거절 → 즉시 다음 단계 제안 + 안내 문구."""
    body = {
        "tenant_id": "org_demo",
        "ad_account_id": "act_demo_001",
        "campaign_id": "camp_esc_reject",
        "now": "2026-06-12T09:00:00+00:00",
    }
    o0 = client.post("/api/management/re-evaluate", json=body).json()
    run_id = o0["run_id"]

    client.post("/api/management/re-evaluate/rejected", json={"run_id": run_id})
    o1 = client.post("/api/management/re-evaluate", json=body).json()
    assert o1["status"] == "escalated"
    assert o1["reason"] == "rejected"
    assert o1["notice"]  # 안내 문구 노출
