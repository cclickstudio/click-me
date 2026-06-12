"""🅱 완료 게이트 테스트 — #1 멱등, #2 만료·stale 차단, #3·#4 강제 측 (§6/§8)."""

from datetime import timedelta

import pytest

from domain.management.contracts.enums import (
    ActionTier,
    ExecutionMode,
    FailureReason,
    FaultMode,
    ResultStatus,
)
from domain.management.contracts.schemas import AUTO_APPROVER, FaultConfig
from tests.management.helpers import (
    NOW,
    FakeWriter,
    build_executor,
    make_action,
    make_proposal,
)

# ── 게이트 #1: 같은 멱등키 10회 → 실행 1건 ──────────────────────


async def test_gate1_same_idempotency_key_10_calls_one_execution():
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer)
    proposal = make_proposal()
    action = make_action(proposal)

    results = [await executor.execute(action, proposal) for _ in range(10)]

    assert len(writer.calls) == 1
    assert all(r.status is ResultStatus.SUCCESS for r in results)
    # 중복 호출은 첫 실행 결과를 그대로 재생한다
    assert {r.result_id for r in results} == {results[0].result_id}


# ── 게이트 #2: 만료·상태버전 변경 제안의 Writer 도달 차단 ──────


async def test_gate2_expired_proposal_never_reaches_writer():
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer)
    proposal = make_proposal(expires_at=NOW - timedelta(minutes=1))
    action = make_action(proposal)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.REJECTED
    assert result.failure_reason is FailureReason.PROPOSAL_EXPIRED
    assert writer.calls == []


async def test_gate2_expired_approval_never_reaches_writer():
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer)
    proposal = make_proposal()
    action = make_action(proposal, expires_at=NOW - timedelta(seconds=1))

    result = await executor.execute(action, proposal)

    assert result.failure_reason is FailureReason.APPROVAL_EXPIRED
    assert writer.calls == []


async def test_gate2_state_version_mismatch_is_stale_proposal():
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer, state_version="sv-43")  # 낙관적 락 우변 변경

    proposal = make_proposal()  # expected_state_version="sv-42"
    action = make_action(proposal)
    result = await executor.execute(action, proposal)

    assert result.failure_reason is FailureReason.STALE_PROPOSAL
    assert writer.calls == []


async def test_policy_version_bump_makes_inflight_action_stale():
    """P2 [안]: 구버전 in-flight 제안은 STALE_PROPOSAL → 새 제안 (자동 승계 금지)."""
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer, policy="approval-policy-v2")

    proposal = make_proposal()
    action = make_action(proposal)
    result = await executor.execute(action, proposal)

    assert result.failure_reason is FailureReason.STALE_PROPOSAL
    assert writer.calls == []


# ── 게이트 #3 (실행 단계): 타 tenant 이중검증 ───────────────────


async def test_gate3_tenant_mismatch_blocked_at_executor():
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer)
    proposal = make_proposal()
    action = make_action(proposal, tenant_id="org-9999")

    result = await executor.execute(action, proposal)

    assert result.failure_reason is FailureReason.TENANT_MISMATCH
    assert writer.calls == []


# ── 게이트 #4 (강제 측): Tier 정책 우회 차단 ────────────────────


async def test_gate4_tier3_with_auto_approver_is_unapproved():
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer)
    proposal = make_proposal(action_tier=ActionTier.TIER_3)
    action = make_action(proposal, action_tier=ActionTier.TIER_3, approver_id=AUTO_APPROVER)

    result = await executor.execute(action, proposal)

    assert result.failure_reason is FailureReason.UNAPPROVED_ACTION
    assert writer.calls == []


async def test_tier2_is_disabled_in_v1():
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer)
    proposal = make_proposal(action_tier=ActionTier.TIER_2)
    action = make_action(proposal, action_tier=ActionTier.TIER_2)

    result = await executor.execute(action, proposal)

    assert result.failure_reason is FailureReason.INVALID_TIER
    assert writer.calls == []


# ── 변조·모드·예산 강제 ─────────────────────────────────────────


async def test_tampered_proposal_hash_detected():
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer)
    proposal = make_proposal()
    action = make_action(proposal)
    tampered = proposal.model_copy(update={"budget_after_krw": 999_999})  # hash 미갱신 변조

    result = await executor.execute(action, tampered)

    assert result.failure_reason is FailureReason.PROPOSAL_HASH_MISMATCH
    assert writer.calls == []


async def test_live_mode_is_disabled():
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer)
    proposal = make_proposal()
    action = make_action(proposal, execution_mode=ExecutionMode.LIVE)

    result = await executor.execute(action, proposal)

    assert result.failure_reason is FailureReason.EXECUTION_MODE_DISABLED
    assert writer.calls == []


async def test_budget_hardcap_blocks_spend():
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer, limit_krw=100_000)
    proposal = make_proposal(
        action_type="adjust_budget", budget_after_krw=60_000, max_total_spend_krw=120_000
    )
    action = make_action(proposal)

    result = await executor.execute(action, proposal)

    assert result.failure_reason is FailureReason.BUDGET_CAP_EXCEEDED
    assert writer.calls == []


async def test_budget_softcap_95_blocks_auto_but_allows_human():
    """P4 [안]: 95% 도달 시 자율(AUTO) 불가 — 사용자 승인 건은 진행."""
    proposal = make_proposal(
        action_type="adjust_budget", budget_after_krw=48_000, max_total_spend_krw=96_000
    )

    writer_auto = FakeWriter()
    executor, _, _, _ = build_executor(writer_auto, limit_krw=100_000)
    auto_action = make_action(proposal, approver_id=AUTO_APPROVER)
    auto_result = await executor.execute(auto_action, proposal)
    assert auto_result.failure_reason is FailureReason.BUDGET_CAP_EXCEEDED
    assert writer_auto.calls == []

    writer_human = FakeWriter()
    executor, _, _, _ = build_executor(writer_human, limit_krw=100_000)
    human_result = await executor.execute(make_action(proposal), proposal)
    assert human_result.status is ResultStatus.SUCCESS
    assert len(writer_human.calls) == 1


# ── 재시도·부분 실패 (P5 → 게이트 #7 연결) ──────────────────────


async def test_write_timeout_retried_with_backoff_then_succeeds():
    """P5 [안]: WRITE_TIMEOUT은 최대 2회 재시도 — 2회 고장 후 3번째 성공."""
    fault = FaultConfig(mode=FaultMode.WRITE_TIMEOUT)
    writer = FakeWriter(fault=fault, fail_times=2)
    executor, audit, _, _ = build_executor(writer)
    proposal = make_proposal()
    action = make_action(proposal)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.SUCCESS
    assert len(writer.calls) == 3
    retries = [e for e in audit.for_approval(action.approval_id) if e.category == "executor.retry"]
    assert len(retries) == 2


async def test_write_timeout_exhausted_fails_with_timeout():
    fault = FaultConfig(mode=FaultMode.WRITE_TIMEOUT)
    writer = FakeWriter(fault=fault, fail_times=10)
    executor, _, _, _ = build_executor(writer)
    proposal = make_proposal()
    action = make_action(proposal)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.FAILED
    assert result.failure_reason is FailureReason.TIMEOUT
    assert len(writer.calls) == 3  # 최초 1회 + 재시도 2회


async def test_rate_limited_waits_and_retries_once():
    fault = FaultConfig(mode=FaultMode.RATE_LIMITED)
    writer = FakeWriter(fault=fault, fail_times=1)
    executor, _, _, _ = build_executor(writer)
    proposal = make_proposal()
    action = make_action(proposal)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.SUCCESS
    assert len(writer.calls) == 2


async def test_review_stuck_maps_to_pending_review():
    """D7: 실행은 했으나 결과 보류 — Meta 비동기 심사 대응."""
    fault = FaultConfig(mode=FaultMode.REVIEW_STUCK)
    writer = FakeWriter(fault=fault, fail_times=1)
    executor, _, _, _ = build_executor(writer)
    proposal = make_proposal()
    action = make_action(proposal)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.SUBMITTED_PENDING_REVIEW


async def test_gate7_partial_failure_halts_and_links_audit():
    """다중 타겟 일부 성공 후 실패 → PARTIAL_FAILURE 정지 + 감사 로그 연결 (게이트 #7)."""
    writer = FakeWriter(fail_targets={"camp-002"})
    executor, audit, _, _ = build_executor(writer)
    proposal = make_proposal(target_object_ids=("camp-001", "camp-002"))
    action = make_action(proposal)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.FAILED
    assert result.failure_reason is FailureReason.PARTIAL_FAILURE
    snapshots = result.platform_response_snapshot["targets"]
    assert [s["target"] for s in snapshots] == ["camp-001", "camp-002"]
    assert snapshots[0]["status"] == "success"
    # 감사 로그가 approval_id로 전 과정을 추적할 수 있어야 한다
    events = audit.for_approval(action.approval_id)
    assert any(e.category == "executor.partial_failure" for e in events)


async def test_failed_execution_does_not_consume_budget_authority():
    fault = FaultConfig(mode=FaultMode.WRITE_TIMEOUT)
    writer = FakeWriter(fault=fault, fail_times=10)
    executor, _, _, budget = build_executor(writer, limit_krw=100_000)
    proposal = make_proposal(
        action_type="adjust_budget", budget_after_krw=10_000, max_total_spend_krw=50_000
    )
    action = make_action(proposal)

    await executor.execute(action, proposal)

    assert budget.spent_krw == 0


async def test_audit_log_has_no_update_or_delete_path():
    """append-only 보증 — 수정·삭제 코드 경로 자체가 없다 (§7)."""
    writer = FakeWriter()
    _, audit, _, _ = build_executor(writer)
    for attr in ("remove", "delete", "update", "clear", "pop"):
        assert not hasattr(audit, attr)


@pytest.mark.parametrize("unsupported", ["replace_creative", "boost_post"])
async def test_unsupported_action_type_rejected(unsupported):
    """v1 Port(D8)는 pause/adjust_budget만 — 그 외는 Writer 도달 전 차단."""
    writer = FakeWriter()
    executor, _, _, _ = build_executor(writer)
    proposal = make_proposal(action_type=unsupported, action_tier=ActionTier.TIER_3)
    action = make_action(proposal)

    result = await executor.execute(action, proposal)

    assert result.failure_reason is FailureReason.UNSUPPORTED_ACTION
    assert writer.calls == []
