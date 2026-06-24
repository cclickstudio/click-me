# 챗 집행 브릿지 — proposal 빌드(해시·검증 통과) + mock executor 실행(hermetic).
import pytest

from domain.chat.adapters.execution import build_chat_proposal, execute_chat_action
from domain.chat.contracts.agent_io import ProposedAction


def _pa(action_type="PAUSE_CAMPAIGN"):
    return ProposedAction(
        action_type=action_type,
        target_campaign_id="camp_1",
        tier="TIER_1",
        requires_approval=True,
        rationale="지출 과다",
    )


def test_build_chat_proposal_passes_hash_and_validation():
    from domain.management.approval import validate_proposal
    from domain.management.contracts.enums import ActionTier
    from domain.management.contracts.policy import DAILY_BUDGET_KRW
    from domain.management.contracts.schemas import verify_proposal_hash

    p = build_chat_proposal(_pa("INCREASE_BUDGET"), tenant_id="org_1")
    assert p is not None
    assert verify_proposal_hash(p)  # finalize_proposal로 해시 채워짐
    assert validate_proposal(p) == []  # 만료·해시·정책버전 이슈 0
    # 예산 계산: before=DAILY_BUDGET_KRW, after=1.5x
    assert p.budget_before_krw == DAILY_BUDGET_KRW
    assert p.budget_after_krw == int(DAILY_BUDGET_KRW * 1.5)
    # tier는 pa.tier("TIER_1")가 아니라 judge_tier(INCREASE_BUDGET)=TIER_3로 판정돼야 함
    assert p.action_tier is ActionTier.TIER_3


def test_build_chat_proposal_rejects_non_executable():
    assert build_chat_proposal(_pa("REPLACE_CREATIVE"), tenant_id="org_1") is None
    assert build_chat_proposal(_pa("CREATE_CAMPAIGN"), tenant_id="org_1") is None


@pytest.mark.asyncio
async def test_execute_chat_action_mock_success():
    from types import SimpleNamespace

    from domain.management.contracts.enums import ExecutionMode
    from domain.management.wiring import build_executor

    # use_mock 환경: executor는 MOCK writer + 인메모리 idempotency/audit
    executor = build_executor(SimpleNamespace(use_mock=True))
    result = await execute_chat_action(
        _pa("PAUSE_CAMPAIGN"),
        tenant_id="org_1",
        approver_id="user_1",
        executor=executor,
        execution_mode=ExecutionMode.MOCK,
    )
    assert result is not None
    # ResultStatus SUCCESS 또는 SUBMITTED_PENDING_REVIEW (mock writer)
    status = result.status.value if hasattr(result.status, "value") else str(result.status)
    assert status in ("success", "submitted_pending_review")


@pytest.mark.asyncio
async def test_execute_chat_action_deferred_returns_none():
    from types import SimpleNamespace

    from domain.management.contracts.enums import ExecutionMode
    from domain.management.wiring import build_executor

    executor = build_executor(SimpleNamespace(use_mock=True))
    result = await execute_chat_action(
        _pa("REPLACE_CREATIVE"),
        tenant_id="org_1",
        approver_id="user_1",
        executor=executor,
        execution_mode=ExecutionMode.MOCK,
    )
    assert result is None  # 위임 액션 → executor 미호출
