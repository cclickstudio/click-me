# /budget/rebalance-commit 라우터 — drift 409·이동량 검증·원자 제안 빌드 확인
"""양쪽 캠페인 drift와 이동량 정합을 검증하고 REBALANCE_BUDGET 제안 1건을 집행하는지 본다."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from core.auth import get_current_user
from core.db import get_db
from domain.management.contracts.enums import FailureReason, ResultStatus
from domain.management.contracts.schemas import ActionResult


class _FakeDB:
    def __init__(self, org_id):
        self._org_id = org_id

    async def scalar(self, stmt, *a, **k):
        if "organization_members" in str(stmt):
            return self._org_id
        return None


class _TwoCampaignReader:
    """list_campaigns 기반 _current_daily_budget 소스 — 예산을 테스트에서 조정."""

    def __init__(self):
        self.budgets = {"camp_low": 50_000, "camp_high": 30_000}

    async def list_campaigns(self, include_archived=False):
        return [
            SimpleNamespace(campaign_id=cid, daily_budget_krw=b)
            for cid, b in self.budgets.items()
        ]


_BODY = {
    "from_campaign_id": "camp_low",
    "to_campaign_id": "camp_high",
    "from_after_krw": 40_000,
    "to_after_krw": 40_000,
    "move_krw": 10_000,
    "shown_from_before_krw": 50_000,
    "shown_to_before_krw": 30_000,
}


@pytest.fixture()
def env(monkeypatch):
    org_id = uuid.uuid4()
    reader = _TwoCampaignReader()
    captured: dict = {}

    async def fake_require_reader(db, org):
        return reader

    async def fake_require_owned(db, org, campaign_id):
        return None

    async def fake_require_ad_account(db, org):
        return "act_test"

    async def fake_require_writer(db, org):
        return object()  # 실 writer 미사용 — executor 자체를 fake로 대체

    class _FakeExecutor:
        async def execute(self, action, proposal):
            captured["action"] = action
            captured["proposal"] = proposal
            return ActionResult(
                result_id="r1",
                approval_id=action.approval_id,
                status=ResultStatus.SUCCESS,
                executed_at=datetime.now(UTC),
                idempotency_key="k",
            )

    # use_mock=False — _current_daily_budget이 데모 고정값이 아닌 fake reader를 보게 한다.
    monkeypatch.setattr(management.settings, "use_mock", False, raising=False)
    monkeypatch.setattr(
        management.settings, "management_execution_mode", "dry_run", raising=False
    )
    monkeypatch.setattr(management, "_require_reader", fake_require_reader)
    monkeypatch.setattr(management, "_require_owned_campaign", fake_require_owned)
    monkeypatch.setattr(management, "_require_ad_account", fake_require_ad_account)
    monkeypatch.setattr(management, "_require_writer", fake_require_writer)
    monkeypatch.setattr(management, "_get_executor", lambda writer=None: _FakeExecutor())

    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: _FakeDB(org_id)
    return TestClient(app, raise_server_exceptions=False), reader, captured


def test_rebalance_commit_builds_atomic_proposal(env):
    client, _reader, captured = env
    res = client.post("/api/management/budget/rebalance-commit", json=_BODY)
    assert res.status_code == 200
    prop = captured["proposal"]
    assert prop.action_type == "REBALANCE_BUDGET"
    assert prop.target_object_ids == ("camp_low", "camp_high")
    assert prop.max_total_spend_krw == 0
    assert prop.evidence_metrics["from_before_krw"] == 50_000
    assert prop.evidence_metrics["to_after_krw"] == 40_000


def test_rebalance_commit_rejects_drift(env):
    client, reader, captured = env
    reader.budgets["camp_low"] = 60_000  # 제안 이후 예산 변동
    res = client.post("/api/management/budget/rebalance-commit", json=_BODY)
    assert res.status_code == 409
    assert "proposal" not in captured  # executor 진입 전 차단


def test_rebalance_commit_rejects_move_mismatch(env):
    client, _reader, captured = env
    res = client.post(
        "/api/management/budget/rebalance-commit", json={**_BODY, "move_krw": 5_000}
    )
    assert res.status_code == 409
    assert "proposal" not in captured


def test_rebalance_commit_rejects_same_campaign(env):
    client, _reader, _captured = env
    res = client.post(
        "/api/management/budget/rebalance-commit",
        json={**_BODY, "to_campaign_id": "camp_low"},
    )
    assert res.status_code == 422


def test_rebalance_commit_rejects_from_after_below_min(env):
    """MIN~MAX full range가 양쪽 after 모두에 적용된다 — from 하한."""
    client, reader, captured = env
    reader.budgets["camp_low"] = 11_000  # from_after=1,000 < MIN(1,521)
    res = client.post(
        "/api/management/budget/rebalance-commit",
        json={
            **_BODY,
            "from_after_krw": 1_000,
            "to_after_krw": 40_000,
            "shown_from_before_krw": 11_000,
        },
    )
    assert res.status_code == 422
    assert "proposal" not in captured


def test_rebalance_commit_rejects_to_after_below_min(env):
    """to_after < MIN도 거부 — 한쪽 하한만 검사하는 회귀 방지."""
    client, reader, captured = env
    reader.budgets["camp_high"] = 400  # to_after=1,400 < MIN(1,521)
    res = client.post(
        "/api/management/budget/rebalance-commit",
        json={
            **_BODY,
            "move_krw": 1_000,
            "from_after_krw": 49_000,
            "to_after_krw": 1_400,
            "shown_to_before_krw": 400,
        },
    )
    assert res.status_code == 422
    assert "proposal" not in captured


def test_rebalance_commit_surfaces_indeterminate_guidance(env, monkeypatch):
    """불확정(PARTIAL 박제) 결과는 generic 실패가 아닌 '확인 후 진행' 안내를 내려준다.

    generic 실패로 보이면 사용자가 새 제안으로 재시도해 pending 다리가 이중 적용될 수 있다.
    """
    client, _reader, _captured = env

    class _IndeterminateExecutor:
        async def execute(self, action, proposal):
            return ActionResult(
                result_id="r1",
                approval_id=action.approval_id,
                status=ResultStatus.FAILED,
                failure_reason=FailureReason.PARTIAL_FAILURE,
                platform_response_snapshot={"targets": [{"indeterminate": True}]},
                executed_at=datetime.now(UTC),
                idempotency_key="k",
            )

    monkeypatch.setattr(
        management, "_get_executor", lambda writer=None: _IndeterminateExecutor()
    )
    res = client.post("/api/management/budget/rebalance-commit", json=_BODY)
    assert res.status_code == 200
    body = res.json()
    assert body.get("indeterminate") is True
    assert "확인" in body["error_message"]  # 재시도 유도가 아닌 상태 확인 안내
