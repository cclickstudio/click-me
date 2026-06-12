"""🅱 단위 검증 — 상태머신·예산 권한·감사 마스킹·eval 지표·서비스 상태 전이."""

import pytest

from domain.management.contracts.enums import FailureReason, ProposalStatus, ResultStatus
from domain.management.evals.regeneration_eval import (
    RegenerationRecord,
    run_eval,
    schema_compliance_rate,
    summarize,
    tool_failure_recovery_rate,
    win_rate,
)
from domain.management.execution.audit_log import MASKED, mask_sensitive
from domain.management.execution.service.execution_service import (
    ExecutionService,
    InMemoryProposalRepository,
)
from domain.management.execution.state_machine import (
    ExecutionRun,
    IllegalTransitionError,
    RunStatus,
)
from domain.management.execution.tier import (
    BudgetAuthority,
    BudgetDecision,
    estimate_max_total_spend,
)
from tests.management.helpers import FakeWriter, build_executor, make_action, make_proposal

# ── 상태머신 ────────────────────────────────────────────────────


def test_state_machine_happy_path():
    run = ExecutionRun(approval_id="appr-1")
    for status in (RunStatus.VALIDATED, RunStatus.RESERVED, RunStatus.CALLING, RunStatus.SUCCEEDED):
        run.advance(status)
    assert run.is_terminal
    assert run.finished_at is not None


def test_state_machine_rejects_illegal_transition():
    run = ExecutionRun(approval_id="appr-1")
    with pytest.raises(IllegalTransitionError):
        run.advance(RunStatus.SUCCEEDED)  # RECEIVED → SUCCEEDED 불가


def test_terminal_state_is_final():
    run = ExecutionRun(approval_id="appr-1")
    run.advance(RunStatus.FAILED)
    with pytest.raises(IllegalTransitionError):
        run.advance(RunStatus.VALIDATED)


def test_halt_preserves_partial_failure_snapshot():
    run = ExecutionRun(approval_id="appr-1")
    run.advance(RunStatus.VALIDATED)
    run.advance(RunStatus.RESERVED)
    run.advance(RunStatus.CALLING)
    run.advance(RunStatus.HALTED, snapshot={"target": "camp-002", "status": "failed"})
    assert run.snapshots[-1]["target"] == "camp-002"


# ── 예산 권한 (P4) ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("spend", "expected"),
    [
        (50_000, BudgetDecision.ALLOW),
        (90_000, BudgetDecision.WARN),  # 90% 경고
        (95_000, BudgetDecision.ESCALATE),  # 95% 자율 불가
        (100_001, BudgetDecision.BLOCK),  # 100% 초과 차단
    ],
)
def test_budget_softcap_thresholds(spend, expected):
    authority = BudgetAuthority(limit_krw=100_000)
    assert authority.evaluate(spend) is expected


def test_budget_authority_accumulates_committed_spend():
    authority = BudgetAuthority(limit_krw=100_000)
    authority.commit(80_000)
    assert authority.evaluate(15_000) is BudgetDecision.ESCALATE


def test_max_total_spend_formula():
    assert estimate_max_total_spend(70_000, 7) == 490_000
    assert estimate_max_total_spend(70_000, 0) == 70_000  # 최소 1일


# ── 감사 로그 마스킹 (게이트 #8 방어선) ─────────────────────────


def test_sensitive_values_are_masked_recursively():
    payload = {
        "access_token": "EAAG...",
        "detail": {"Authorization": "Bearer xyz", "campaign_id": "camp-001"},
    }
    masked = mask_sensitive(payload)
    assert masked["access_token"] == MASKED
    assert masked["detail"]["Authorization"] == MASKED
    assert masked["detail"]["campaign_id"] == "camp-001"


# ── 재생성 eval 지표 ────────────────────────────────────────────


def _record(**overrides) -> RegenerationRecord:
    fields = {
        "case_id": "case-1",
        "baseline_score": 0.5,
        "candidate_scores": (0.7,),
        "guardrail_passed": True,
    }
    fields.update(overrides)
    return RegenerationRecord(**fields)


def test_win_rate_counts_improvements_only():
    records = [
        _record(candidate_scores=(0.7,)),  # win
        _record(case_id="case-2", candidate_scores=(0.4,)),  # lose
        _record(case_id="case-3", candidate_scores=()),  # 제안 실패 = lose
    ]
    assert win_rate(records) == pytest.approx(1 / 3)


def test_recovery_rate_only_considers_failed_tool_cases():
    records = [
        _record(tool_calls=3, tool_failures=1, recovered=True),
        _record(
            case_id="case-2",
            tool_calls=3,
            tool_failures=2,
            recovered=False,
            failure_reason=FailureReason.TIMEOUT,
        ),
        _record(case_id="case-3", tool_calls=2, tool_failures=0),
    ]
    assert tool_failure_recovery_rate(records) == pytest.approx(0.5)


def test_schema_compliance_counts_only_reached_proposals():
    records = [
        _record(proposal_valid=True),
        _record(case_id="case-2", proposal_valid=False),
        _record(case_id="case-3", candidate_scores=(), proposal_valid=True),  # 미도달 — 제외
    ]
    assert schema_compliance_rate(records) == pytest.approx(0.5)


def test_summary_reports_target_and_fixture_version():
    report = summarize([_record()], fixture_version="v1")
    assert report.fixture_version == "v1"
    assert report.win_rate == 1.0
    assert report.schema_compliance_rate == 1.0
    assert report.meets_win_rate_target


def test_run_eval_loads_v1_fixture_and_scores_it():
    """B-4 실행 진입점 — cases_v1.json 8케이스 기계 채점."""
    report = run_eval("v1")
    assert report.total_cases == 8
    assert report.fixture_version == "v1"
    assert 0.0 <= report.win_rate <= 1.0
    assert report.failure_breakdown.get(str(FailureReason.TIMEOUT)) == 1


# ── ExecutionService ────────────────────────────────────────────


async def test_service_rejects_unknown_proposal():
    writer = FakeWriter()
    executor, audit, _, _ = build_executor(writer)
    service = ExecutionService(executor, InMemoryProposalRepository(), audit)
    action = make_action(make_proposal())  # repo에 저장 안 함

    result = await service.handle(action)

    assert result.status is ResultStatus.REJECTED
    assert result.failure_reason is FailureReason.STALE_PROPOSAL
    assert writer.calls == []


async def test_service_marks_proposal_executed_on_success():
    writer = FakeWriter()
    executor, audit, _, _ = build_executor(writer)
    repo = InMemoryProposalRepository()
    proposal = make_proposal()
    repo.save(proposal)
    service = ExecutionService(executor, repo, audit)

    result = await service.handle(make_action(proposal))

    assert result.status is ResultStatus.SUCCESS
    assert repo.get(proposal.proposal_id).status is ProposalStatus.EXECUTED
