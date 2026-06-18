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
