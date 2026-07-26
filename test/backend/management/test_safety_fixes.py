# management 실집행 안전 6종 회귀 방지 — 예산캡 서버재계산·LIVE opt-in·Meta 500 방지·생성 상한
"""C-1~M-5 안전 픽스 회귀 테스트.

- C-1: ActivateRequest에 org_id 필드 부재(타 org 크레딧 조회 결함 제거).
- C-2: LIVE는 기본 executor에서 봉인, opt-in에서만 통과.
- C-3: 지출 증가 액션의 max_total_spend_krw 서버 재계산(위조 우회 차단).
- H-3: Meta 장애를 raw 500이 아닌 명확한 HTTP로 변환.
- M-5: 생성 제안 일예산 상한(_MAX_DAILY_BUDGET_KRW) 초과 시 422.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from core.auth import get_current_user
from core.db import get_db
from domain.management.adapters.meta.client import MetaApiError
from domain.management.contracts.enums import ExecutionMode, FailureReason, ResultStatus
from domain.management.execution.executor import Executor
from domain.management.execution.tier import estimate_max_total_spend

from .helpers import FakeWriter, build_executor, make_action, make_proposal


# ── C-3: 지출 증가 액션 예산 서버 재계산 ────────────────────────────
def test_effective_spend_recomputes_increase_budget():
    # 위조 제안(max_total_spend_krw=0)이라도 budget_after×7일로 하한 재계산된다.
    proposal = make_proposal(
        action_type="INCREASE_BUDGET",
        budget_after_krw=100_000_000,
        max_total_spend_krw=0,
    )
    effective = Executor._effective_spend(proposal)
    assert effective == estimate_max_total_spend(100_000_000, 7) == 700_000_000


def test_effective_spend_keeps_reported_for_rebalance_and_decrease():
    # 총액 불변/감소 액션은 신고값을 그대로 유지(재계산 안 함).
    for action_type in ("REBALANCE_BUDGET", "DECREASE_BUDGET"):
        proposal = make_proposal(
            action_type=action_type,
            budget_after_krw=100_000_000,
            max_total_spend_krw=123,
        )
        assert Executor._effective_spend(proposal) == 123


async def test_forged_increase_budget_blocked_by_recomputed_cap():
    # 위조 INCREASE_BUDGET(신고 0)이 서버 재계산(7억)으로 하드캡(1백만)을 초과해 차단된다.
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer, limit_krw=1_000_000)
    proposal = make_proposal(
        action_type="INCREASE_BUDGET",
        budget_after_krw=100_000_000,
        max_total_spend_krw=0,
    )
    action = make_action(proposal)

    result = await executor.execute(action, proposal)

    assert result.failure_reason is FailureReason.BUDGET_CAP_EXCEEDED
    assert writer.calls == []


def test_effective_spend_recomputes_escalation_actions():
    # 에스컬레이션 지출 증가 액션도 위조 0-신고를 서버 재계산으로 덮는다(코드리뷰 반영).
    for action_type in ("EXPAND_AUDIENCE", "CHANGE_BID_STRATEGY"):
        proposal = make_proposal(
            action_type=action_type,
            budget_after_krw=100_000_000,
            max_total_spend_krw=0,
        )
        assert Executor._effective_spend(proposal) == estimate_max_total_spend(100_000_000, 7)


# ── C-2: LIVE opt-in 게이트 ─────────────────────────────────────────
async def test_live_blocked_in_default_executor():
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer)  # 기본 allowed_modes (LIVE 불포함)
    proposal = make_proposal()
    action = make_action(proposal, execution_mode=ExecutionMode.LIVE)

    result = await executor.execute(action, proposal)

    assert result.failure_reason is FailureReason.EXECUTION_MODE_DISABLED
    assert writer.calls == []


async def test_live_passes_gate_when_opted_in():
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer, allow_live=True)
    proposal = make_proposal()
    action = make_action(proposal, execution_mode=ExecutionMode.LIVE)

    result = await executor.execute(action, proposal)

    assert result.failure_reason is not FailureReason.EXECUTION_MODE_DISABLED
    assert writer.calls != []
    assert result.status is ResultStatus.SUCCESS


# ── C-1: ActivateRequest 스키마에 org_id 부재 ────────────────────────
def test_activate_request_has_no_org_id_field():
    # 타 org 크레딧 조회 결함 제거 — 클라이언트가 org_id를 실을 수 없어야 한다.
    assert "org_id" not in management.ActivateRequest.model_fields


# ── H-3: Meta 장애 → 404 변환 (delivery-status) ──────────────────────
class _FailingReader:
    """get_delivery_status_detail가 MetaApiError(code=100)를 던지는 가짜 리더."""

    async def get_delivery_status_detail(self, campaign_id: str):
        raise MetaApiError(code=100, subcode=33, message="does not exist")

    async def get_account_funding(self):  # pragma: no cover — 도달 전 예외
        return None

    async def get_spend_cap(self, campaign_id: str):  # pragma: no cover
        return None


def test_delivery_status_meta_error_becomes_404():
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[management._request_reader] = lambda: _FailingReader()
    client = TestClient(app, raise_server_exceptions=False)

    res = client.get("/api/management/campaigns/camp-x/delivery-status")

    assert res.status_code == 404


# ── M-5: 생성 제안 일예산 상한 422 ──────────────────────────────────
@pytest.fixture()
def _create_proposal_client(monkeypatch):
    org_id = uuid.uuid4()

    async def _fake_org_id(user, db):
        return org_id

    async def _fake_reader(db, oid):
        return SimpleNamespace()

    async def _fake_policy(reader):
        return SimpleNamespace()

    def _fake_min(objective, policy):
        return 1_000

    monkeypatch.setattr(management, "_require_org_id", _fake_org_id)
    monkeypatch.setattr(management, "_require_reader", _fake_reader)
    monkeypatch.setattr(management, "get_campaign_policy", _fake_policy)
    monkeypatch.setattr(management, "min_daily_budget_for", _fake_min)

    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), role="USER"
    )
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    return TestClient(app, raise_server_exceptions=False)


def test_create_proposal_rejects_over_max_daily_budget(_create_proposal_client):
    body = {
        "name": "테스트",
        "objective": "traffic",
        "daily_budget_krw": management._MAX_DAILY_BUDGET_KRW + 1,
        "run_days": 7,
    }
    res = _create_proposal_client.post("/api/management/campaigns/create-proposal", json=body)

    assert res.status_code == 422
    assert "넘을 수 없어요" in res.json()["detail"]
