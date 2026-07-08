# /approve 승인 플레인 폐쇄 — 무인증 401·org 검증·approver 서버 주입·원장 기록
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from management.helpers import make_proposal

from api.routers import management
from core.db import get_db
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION
from domain.management.execution.approval_stores import InMemoryApprovalStore


class _FakeDB:
    def __init__(self, org_id=None):
        self._org_id = org_id

    async def scalar(self, stmt, *a, **k):
        if "organization_members" in str(stmt):
            return self._org_id
        return None


def _fresh_proposal(tenant_id: str):
    """실시간 검증(만료·정책버전)을 통과하는 제안 — helpers.NOW(과거)가 아닌 현재 기준."""
    now = datetime.now(UTC)
    return make_proposal(
        tenant_id=tenant_id,
        approval_policy_version=APPROVAL_POLICY_VERSION,
        metrics_as_of=now,
        expires_at=now + timedelta(hours=1),
    )


def test_approve_unauthenticated_401():
    """무인증 실 HTTP 요청 — get_current_user를 오버라이드하지 않고 401을 확인한다."""
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_db] = lambda: _FakeDB()  # auth는 실물, db만 지연 페이크
    client = TestClient(app)
    res = client.post("/api/management/approve", json={"proposal": {}, "approved": True})
    assert res.status_code == 401


def test_approval_request_has_no_approver_id_field():
    """approver_id는 서버 주입 — 요청 모델에서 필드 자체가 제거되고 extra는 무시된다."""
    proposal = _fresh_proposal("org-x")
    body = management.ApprovalRequest(proposal=proposal, approved=True, approver_id="attacker")
    assert not hasattr(body, "approver_id")


async def test_approve_cross_org_403(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", True, raising=False)
    org = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    proposal = _fresh_proposal("org-someone-else")
    body = management.ApprovalRequest(proposal=proposal, approved=True)
    with pytest.raises(HTTPException) as exc:
        await management.approve_proposal(body, user=user, db=_FakeDB(org_id=org))
    assert exc.value.status_code == 403


async def test_approve_injects_server_approver_and_writes_ledger(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", True, raising=False)
    store = InMemoryApprovalStore()
    monkeypatch.setattr(management, "_APPROVAL_STORE", store)
    org = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    proposal = _fresh_proposal(str(org))
    body = management.ApprovalRequest(proposal=proposal, approved=True)
    out = await management.approve_proposal(body, user=user, db=_FakeDB(org_id=org))
    action = out["approved_action"]
    assert action["approver_id"] == str(user.id)  # 서버 주입 — 클라이언트 지정 불가
    assert await store.get(action["approval_id"]) is not None  # 원장 기록됨


async def test_approve_demo_sentinel_allowed_for_any_org(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", True, raising=False)
    store = InMemoryApprovalStore()
    monkeypatch.setattr(management, "_APPROVAL_STORE", store)
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    proposal = _fresh_proposal(management.TENANT_ID)  # 시연 센티넬 — org 불일치 면제
    body = management.ApprovalRequest(proposal=proposal, approved=True)
    out = await management.approve_proposal(body, user=user, db=_FakeDB(org_id=uuid.uuid4()))
    assert out["status"] == "approved"
