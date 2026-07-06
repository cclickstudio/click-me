# executor → 롱텀 메모리 기록 콜백 — 성공 시 1회 호출·거부/재생 시 미호출·실패 무해성 검증
"""history_recorder는 실행이 '신규로 확정'된 경우에만 불린다(재생·거부 제외).

콜백 내부 예외는 실행 결과를 바꾸지 않는다(best-effort). DB 없이 콜백 주입으로 검증.
"""

from datetime import timedelta

from management.helpers import NOW, FakeWriter, make_action, make_proposal

from domain.management.contracts.enums import ResultStatus
from domain.management.execution.executor import Executor
from domain.management.execution.tier import BudgetAuthority


def _build(writer: FakeWriter, recorder):
    from management.helpers import (
        POLICY_VERSION,
        STATE_VERSION,
        InMemoryAuditLog,
        InMemoryIdempotencyStore,
        _no_sleep,
    )

    async def state_provider(_ad_account_id: str) -> str:
        return STATE_VERSION

    budget = BudgetAuthority(limit_krw=1_000_000)
    return Executor(
        writer,
        idempotency=InMemoryIdempotencyStore(),
        audit=InMemoryAuditLog(),
        budget_for=lambda _t: budget,
        state_version_provider=state_provider,
        current_policy_version=POLICY_VERSION,
        clock=lambda: NOW,
        sleep=_no_sleep,
        history_recorder=recorder,
    )


async def test_recorder_called_once_on_success_and_not_on_replay():
    calls = []

    async def recorder(action, proposal, result):
        calls.append((proposal.action_type, result.status))

    executor = _build(FakeWriter(), recorder)
    proposal = make_proposal()
    action = make_action(proposal)

    first = await executor.execute(action, proposal)
    replay = await executor.execute(action, proposal)  # 멱등 재생 — 기록 안 함

    assert first.status is ResultStatus.SUCCESS
    assert replay.result_id == first.result_id
    assert len(calls) == 1
    assert calls[0][1] is ResultStatus.SUCCESS


async def test_recorder_not_called_on_rejection():
    calls = []

    async def recorder(action, proposal, result):
        calls.append(result.status)

    executor = _build(FakeWriter(), recorder)
    proposal = make_proposal(expires_at=NOW - timedelta(minutes=1))  # 만료 → 거부
    action = make_action(proposal)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.REJECTED
    assert calls == []


async def test_recorder_failure_does_not_change_result():
    async def recorder(action, proposal, result):
        raise RuntimeError("기록 저장소 장애")

    executor = _build(FakeWriter(), recorder)
    proposal = make_proposal()
    action = make_action(proposal)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.SUCCESS  # 기록 실패가 결과를 바꾸지 않는다
