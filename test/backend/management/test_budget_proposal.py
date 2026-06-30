# 예산 proposal 빌더 — INCREASE/DECREASE 판정·budget 결속·hash 검증(순수, DB·LLM 미경유).
import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from api.routers.management import _build_budget_proposal
from core.auth import get_current_user
from core.db import get_db
from domain.management.contracts.enums import ActionTier
from domain.management.contracts.schemas import verify_proposal_hash


class _FakeScalars:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return _FakeScalars(self._value)


class _FakeDB:
    def __init__(self, org_id):
        self.org_id = org_id
        self.campaign = SimpleNamespace(tenant_id=str(org_id), daily_budget_krw=40_000, name="x")
        self.conn = SimpleNamespace(ad_account_id="act_1")

    async def scalar(self, stmt, *a, **k):
        s = str(stmt)
        if "organization_members" in s:
            return self.org_id
        if "management_meta_connections" in s:
            return self.conn
        return None

    async def execute(self, stmt, *a, **k):
        return _FakeResult(self.campaign)


class _MutableBudgetReader:
    def __init__(self, budget):
        self.budget = budget

    async def list_campaigns(self, include_archived=False):
        return [
            SimpleNamespace(
                campaign_id="camp_1",
                name="Campaign 1",
                state="active",
                daily_budget_krw=self.budget,
            )
        ]


def test_increase_proposal():
    # 빌더는 선언된 action_type을 그대로 쓴다(방향 재판정 안 함). 검증·방향강제는 엔드포인트.
    p = _build_budget_proposal(
        tenant_id="org_1",
        ad_account_id="act_1",
        campaign_id="c_1",
        action_type="INCREASE_BUDGET",
        budget_before_krw=40000,
        new_daily_budget_krw=50000,
    )
    assert p.action_type == "INCREASE_BUDGET"
    assert p.action_tier == ActionTier.TIER_3
    assert p.budget_before_krw == 40000 and p.budget_after_krw == 50000
    # 추가 지출 권한은 증분만(50000-40000)*7 — 전체(50000*7) 아님(Codex [medium]).
    assert p.max_total_spend_krw == (50000 - 40000) * 7
    assert verify_proposal_hash(p)


def test_decrease_proposal():
    p = _build_budget_proposal(
        tenant_id="org_1",
        ad_account_id="act_1",
        campaign_id="c_1",
        action_type="DECREASE_BUDGET",
        budget_before_krw=50000,
        new_daily_budget_krw=30000,
    )
    assert p.action_type == "DECREASE_BUDGET"
    assert p.action_tier == ActionTier.TIER_1
    assert p.budget_after_krw == 30000
    # 감액은 추가 지출 권한 0 — cap에 막히거나 권한 소모하면 안 됨(Codex [medium]).
    assert p.max_total_spend_krw == 0


def test_budget_commit_rejects_stale_preview_before_executor(monkeypatch):
    org_id = uuid.uuid4()
    reader = _MutableBudgetReader(40_000)
    executor_calls = []

    async def fake_require_reader(db, org):
        assert org == org_id
        return reader

    def fail_get_executor(writer=None):
        executor_calls.append(("factory", writer))
        raise AssertionError("executor must not be selected for a stale budget commit")

    monkeypatch.setattr(management.settings, "use_mock", False, raising=False)
    monkeypatch.setattr(management, "_require_reader", fake_require_reader)
    monkeypatch.setattr(management, "_get_executor", fail_get_executor)

    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: _FakeDB(org_id)

    with TestClient(app, raise_server_exceptions=False) as client:
        preview = client.post(
            "/api/management/campaigns/camp_1/budget-proposal",
            json={
                "action": "increase_budget",
                "new_daily_budget_krw": 50_000,
                "shown_budget_before_krw": 40_000,
            },
        )
        assert preview.status_code == 200
        assert preview.json()["proposal"]["budget_before_krw"] == 40_000

        reader.budget = 60_000
        stale = client.post(
            "/api/management/campaigns/camp_1/budget-commit",
            json={
                "action": "increase_budget",
                "new_daily_budget_krw": 50_000,
                "shown_budget_before_krw": 40_000,
            },
        )

    assert stale.status_code == 409
    assert executor_calls == []
