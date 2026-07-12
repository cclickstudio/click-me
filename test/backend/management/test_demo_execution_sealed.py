# 시연(org_demo) 집행 경로가 use_mock=False+live에서도 실 Meta write에 도달 못 함을 봉인 검증
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from management.helpers import make_proposal

from api.routers import management
from domain.management.contracts.enums import ExecutionMode
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION
from domain.management.contracts.schemas import ApprovedAction
from domain.management.execution.approval_stores import InMemoryApprovalStore


class _FakeDB:
    """org 조회(db.scalar)만 흉내 — 시연은 org 불일치 면제라 아무 org나 통과."""

    def __init__(self, org_id=None):
        self._org_id = org_id

    async def scalar(self, stmt, *a, **k):
        if "organization_members" in str(stmt):
            return self._org_id
        return None

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _fresh_proposal(tenant_id: str, **overrides):
    """실시간 검증(만료·정책버전)을 통과하는 제안 — helpers.NOW(과거)가 아닌 현재 기준."""
    now = datetime.now(UTC)
    fields = {
        "tenant_id": tenant_id,
        "approval_policy_version": APPROVAL_POLICY_VERSION,
        "metrics_as_of": now,
        "expires_at": now + timedelta(hours=1),
    }
    fields.update(overrides)
    return make_proposal(**fields)


def _live_settings(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", False, raising=False)
    monkeypatch.setattr(management.settings, "management_execution_mode", "live", raising=False)


def test_demo_executor_writer_is_dry_run_even_when_live(monkeypatch):
    """봉인 핵심 — use_mock=False+live에서도 시연 executor의 writer는 DRY_RUN(미전송)."""
    _live_settings(monkeypatch)
    monkeypatch.setattr(management, "_demo_executor_instance", None)

    demo = management._demo_executor()
    assert demo._writer._mode is ExecutionMode.DRY_RUN  # 시연 writer는 실 write 불가
    assert demo._writer._client is None  # live 토큰이 있어도 클라이언트 미구성(미전송)

    # 대조 — 봉인이 없었다면 전역 build_writer는 실 write 가능(LIVE) writer를 냈을 것.
    assert management.build_writer(management.settings)._mode is ExecutionMode.LIVE


async def test_approve_pins_demo_to_mock_and_leaves_normal_live(monkeypatch):
    """시연 승인은 execution_mode를 MOCK로 고정, 실 제안은 settings 실행 모드(live) 유지."""
    _live_settings(monkeypatch)
    monkeypatch.setattr(management, "_APPROVAL_STORE", InMemoryApprovalStore())
    org = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")

    demo_out = await management.approve_proposal(
        management.ApprovalRequest(proposal=_fresh_proposal(management.TENANT_ID), approved=True),
        user=user,
        db=_FakeDB(org_id=org),
    )
    assert demo_out["approved_action"]["execution_mode"] == "mock"  # 원장이 LIVE를 실을 수 없음

    real_out = await management.approve_proposal(
        management.ApprovalRequest(proposal=_fresh_proposal(str(org)), approved=True),
        user=user,
        db=_FakeDB(org_id=org),
    )
    assert real_out["approved_action"]["execution_mode"] == "live"  # 정상 경로 불변


async def test_demo_approve_execute_succeeds_in_mock_under_live(monkeypatch):
    """live 설정에서도 시연 승인→집행 왕복이 MOCK로 성립하고, 실행 writer는 미전송(DRY_RUN)."""
    _live_settings(monkeypatch)
    monkeypatch.setattr(management, "_APPROVAL_STORE", InMemoryApprovalStore())
    monkeypatch.setattr(management, "_demo_executor_instance", None)  # 새 원장을 잡도록 재빌드
    org = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    # executor의 state 버전 provider(wiring.state_version_v1)가 "state_v1"이라 제안도 그에 맞춘다.
    proposal = _fresh_proposal(management.TENANT_ID, expected_state_version="state_v1")

    approved = await management.approve_proposal(
        management.ApprovalRequest(proposal=proposal, approved=True),
        user=user,
        db=_FakeDB(org_id=org),
    )
    action = ApprovedAction.model_validate(approved["approved_action"])
    assert action.execution_mode is ExecutionMode.MOCK

    out = await management.execute(
        management.ExecuteRequest(approved_action=action, proposal=proposal),
        user=user,
        db=_FakeDB(org_id=org),
    )
    # 게이트 #5(원장 대조) 통과 + 집행 성공 — 단, 실 write는 없다(DRY_RUN writer).
    assert out["result"]["status"] == "success"
    assert management._demo_executor()._writer._mode is ExecutionMode.DRY_RUN
