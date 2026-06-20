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


def test_regenerate_returns_awaiting_selection(client):
    """FIX 1 — /regenerate는 AWAITING_SELECTION을 그대로 반환한다(자동 선택 금지)."""
    run = client.get("/api/management/run?fault=bid_loss").json()
    assert run["diagnosis"] is not None

    res = client.post("/api/management/regenerate", json={"diagnosis": run["diagnosis"]})
    assert res.status_code == 200
    body = res.json()
    # 크리에이티브 진단 → AWAITING_SELECTION 반환, 자동 선택·패키징 없음
    assert body["kind"] == "awaiting_selection"
    assert body["selection_token"]
    assert isinstance(body["candidates"], list)
    assert len(body["candidates"]) >= 1
    # 제안이 포함돼 있으면 안 된다 (아직 사람이 선택하지 않았으므로)
    assert "proposal" not in body


def _build_proposal_via_package(diagnosis_json: dict) -> dict:
    """AWAITING_SELECTION을 받아 idx-0 후보를 선택·package해 제안 dict를 반환한다.

    동기 컨텍스트(TestClient)에서 비동기 agent를 호출하기 위해 asyncio.run()을 사용한다.
    """
    import asyncio

    from domain.management.agents.outcome import OutcomeKind
    from domain.management.agents.regeneration import RemediationContext
    from domain.management.agents.regeneration_tools import build_regeneration_agent
    from domain.management.contracts.policy import APPROVAL_POLICY_VERSION, DAILY_BUDGET_KRW
    from domain.management.contracts.schemas import DiagnosisResult

    async def _run():
        agent = build_regeneration_agent()
        dx = DiagnosisResult.model_validate(diagnosis_json)
        ctx = RemediationContext(
            ad_account_id="act_demo_001",
            target_object_ids=(dx.campaign_id,),
            budget_before_krw=DAILY_BUDGET_KRW,
            budget_after_krw=int(DAILY_BUDGET_KRW * 1.5),
            run_days=7,
            expected_state_version="state_v1",
            approval_policy_version=APPROVAL_POLICY_VERSION,
            action_type="REPLACE_CREATIVE",
        )
        outcome = await agent.rank(dx, ctx)
        assert outcome.kind is OutcomeKind.AWAITING_SELECTION
        pkg = await agent.package(
            outcome.selection_token,
            tenant_id=dx.tenant_id,
            selected_id=outcome.candidates[0]["candidate_id"],
        )
        return pkg.proposal.model_dump(mode="json")

    return asyncio.run(_run())


def test_full_cycle_run_regenerate_approve_execute(client):
    """선택(package) 포함 풀 사이클 — AWAITING_SELECTION → 후보 선택 → 제안 → 승인 → 집행."""
    run = client.get("/api/management/run?fault=bid_loss").json()
    assert run["diagnosis"] is not None

    regen = client.post("/api/management/regenerate", json={"diagnosis": run["diagnosis"]}).json()
    assert regen["kind"] == "awaiting_selection"

    proposal = _build_proposal_via_package(run["diagnosis"])
    assert proposal["action_type"] == "REPLACE_CREATIVE"
    assert proposal["evidence_metrics"]["selected_candidate_id"]

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
    """감사 이벤트 — 풀 사이클(package 포함) 후 executor.completed 확인."""
    run = client.get("/api/management/run?fault=bid_loss").json()
    proposal = _build_proposal_via_package(run["diagnosis"])

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
