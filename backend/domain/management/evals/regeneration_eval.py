"""🅱 재생성 품질 eval — 승률·가드레일 통과율·tool-call 성공률·schema 준수율·복구율.

목표: 재생성 개선율(승률) ≥ 70% (PRD §5.2). 점수 보고 시 픽스처 버전 병기 (§9.0).
픽스처: ``evals/fixtures/regeneration/cases_<버전>.json`` — 🅱 광고 케이스.
단서: 시뮬 점수 ↔ 실제 성과 상관 미검증 — 발표에서 정직하게 공개 (§7).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from domain.management.agents.outcome import OutcomeKind
from domain.management.agents.regeneration import (
    MAX_CANDIDATES,
    CreativeCandidate,
    RemediationAgent,
    RemediationContext,
    RiskAppetite,
    decide_action,
)
from domain.management.agents.selection import InMemorySelectionRoundStore
from domain.management.contracts.enums import FailureReason
from domain.management.contracts.schemas import (
    ActionProposal,
    DiagnosisResult,
    verify_proposal_hash,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

WIN_RATE_TARGET = 0.70  # PRD §5.2

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "regeneration"


@dataclass(frozen=True)
class RegenerationRecord:
    """재생성 시도 1건의 채점 입력 — eval fixture에서 로드."""

    case_id: str
    baseline_score: float  # 원본 시안의 시뮬 점수
    candidate_scores: tuple[float, ...]  # 생존 후보들의 시뮬 점수
    guardrail_passed: bool  # 금지표현·상한·점수 가드 통과 여부
    proposal_valid: bool = True  # 패키징된 제안의 ActionProposal 스키마 적합 여부
    tool_calls: int = 0
    tool_failures: int = 0
    recovered: bool = True  # tool 실패 발생 시 재시도/폴백으로 제안까지 도달했는가
    failure_reason: FailureReason | None = None  # 실패 시 기계 채점용 enum
    expected_action: str | None = None  # 기대 처방 (None = 관망 기대)
    chosen_action: str | None = None  # agent가 실제로 고른 처방
    action_labeled: bool = False  # action 선택 채점 대상 여부 (None=관망과 미라벨 구분)
    fixture_version: str = "v1"


@dataclass(frozen=True)
class EvalReport:
    fixture_version: str
    total_cases: int
    win_rate: float
    guardrail_pass_rate: float
    schema_compliance_rate: float
    tool_call_success_rate: float
    tool_failure_recovery_rate: float
    action_selection_accuracy: float
    failure_breakdown: dict[str, int]
    meets_win_rate_target: bool


def win_rate(records: Sequence[RegenerationRecord]) -> float:
    """최고 후보 점수 > 원본 점수인 케이스 비율 — 개선율의 정의."""
    if not records:
        return 0.0
    wins = sum(
        1 for r in records if r.candidate_scores and max(r.candidate_scores) > r.baseline_score
    )
    return wins / len(records)


def guardrail_pass_rate(records: Sequence[RegenerationRecord]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r.guardrail_passed) / len(records)


def schema_compliance_rate(records: Sequence[RegenerationRecord]) -> float:
    """제안까지 도달한 케이스 중 ActionProposal 스키마 적합 비율 (B-4 schema 준수율)."""
    reached = [r for r in records if r.candidate_scores]
    if not reached:
        return 1.0
    return sum(1 for r in reached if r.proposal_valid) / len(reached)


def tool_call_success_rate(records: Sequence[RegenerationRecord]) -> float:
    total_calls = sum(r.tool_calls for r in records)
    if total_calls == 0:
        return 1.0
    total_failures = sum(r.tool_failures for r in records)
    return (total_calls - total_failures) / total_calls


def tool_failure_recovery_rate(records: Sequence[RegenerationRecord]) -> float:
    """tool 실패가 있었던 케이스 중 제안까지 복구된 비율 — B-4 차별화 지표."""
    failed = [r for r in records if r.tool_failures > 0]
    if not failed:
        return 1.0
    return sum(1 for r in failed if r.recovered) / len(failed)


def action_selection_accuracy(records: Sequence[RegenerationRecord]) -> float:
    """라벨된 케이스 중 agent의 처방이 기대 처방과 일치한 비율 (None=관망도 정답 대상)."""
    labeled = [r for r in records if r.action_labeled]
    if not labeled:
        return 1.0
    return sum(1 for r in labeled if r.chosen_action == r.expected_action) / len(labeled)


def guard_pass_rate(*, kept: int, total: int) -> float:
    """가드 통과율 — 프로세스 지표(스펙 §11)."""
    return kept / total if total else 0.0


def execution_blocked_by_budget_rate(failure_reasons: list[str]) -> float:
    """executor BUDGET_CAP_EXCEEDED 집계 → v1.5 budget preflight 칼리브레이션(스펙 §11)."""
    if not failure_reasons:
        return 0.0
    blocked = sum(1 for r in failure_reasons if r == "BUDGET_CAP_EXCEEDED")
    return blocked / len(failure_reasons)


def rate(numerator: int, denominator: int) -> float:
    """HITL 선택 메트릭 공용 비율 — outcome 로그 집계로 산출(스펙 §11):
    awaiting_selection_emit_rate(AWAITING_SELECTION/전체 rank),
    selection_package_success_rate(PROPOSED/claim 시도),
    expired_selection_reject_rate(만료 거부/claim 시도)."""
    return numerator / denominator if denominator else 0.0


def failure_breakdown(records: Sequence[RegenerationRecord]) -> dict[str, int]:
    counter = Counter(str(r.failure_reason) for r in records if r.failure_reason is not None)
    return dict(counter)


def summarize(records: Sequence[RegenerationRecord], fixture_version: str = "v1") -> EvalReport:
    win_rate_value = win_rate(records)
    return EvalReport(
        fixture_version=fixture_version,
        total_cases=len(records),
        win_rate=win_rate_value,
        guardrail_pass_rate=guardrail_pass_rate(records),
        schema_compliance_rate=schema_compliance_rate(records),
        tool_call_success_rate=tool_call_success_rate(records),
        tool_failure_recovery_rate=tool_failure_recovery_rate(records),
        action_selection_accuracy=action_selection_accuracy(records),
        failure_breakdown=failure_breakdown(records),
        meets_win_rate_target=win_rate_value >= WIN_RATE_TARGET,
    )


# ── fixture 로드 + 실행 진입점 ──────────────────────────────────


def load_records(fixture_version: str = "v1") -> list[RegenerationRecord]:
    """``fixtures/regeneration/cases_<버전>.json`` 에서 채점 입력을 로드한다."""
    path = FIXTURES_DIR / f"cases_{fixture_version}.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    records = []
    for case in cases:
        reason = case.pop("failure_reason", None)
        scores = tuple(case.pop("candidate_scores"))
        records.append(
            RegenerationRecord(
                **case,
                candidate_scores=scores,
                failure_reason=FailureReason(reason) if reason else None,
                fixture_version=fixture_version,
            )
        )
    return records


def run_eval(fixture_version: str = "v1") -> EvalReport:
    """fixture 1벌을 채점해 리포트 반환 — 보고 시 픽스처 버전 병기 (§9.0)."""
    records = load_records(fixture_version)
    return summarize(records, fixture_version=fixture_version)


# ── agent 실행형 하니스 — 진짜 RemediationAgent를 fixture 진단에 돌려 채점 ──


@dataclass
class _CountingGenerator:
    """결정론 생성 tool 스텁 — 호출·실패 횟수를 계측하며 고장을 주입한다."""

    candidates: list[CreativeCandidate]
    fail_times: int = 0
    calls: int = 0
    failures: int = 0

    async def generate(self, diagnosis: DiagnosisResult, count: int) -> list[CreativeCandidate]:
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            self.failures += 1
            raise TimeoutError("생성 tool 고장 주입")
        return self.candidates


_EVAL_CONTEXT_DEFAULTS = {
    "ad_account_id": "act_eval",
    "target_object_ids": ("camp-eval-1",),
    "budget_before_krw": 50_000,
    "budget_after_krw": 50_000,
    "run_days": 7,
    "expected_state_version": "sv-eval",
    "approval_policy_version": "approval-policy-v1",
    "action_type": "REPLACE_CREATIVE",
}


async def _drive_to_proposal(
    agent: RemediationAgent, diagnosis: DiagnosisResult, context: RemediationContext
) -> ActionProposal | None:
    """rank()→(크리에이티브면 idx 0 자동선택)package() → 제안 또는 빈손.

    채점이 사라진 v1 — 순위는 4-3 idx 통과이므로 eval은 최상위 후보를 자동 선택해
    제안 도달 여부(프로세스 지표)만 관측한다. 실제 HITL 선택은 데모/프론트에서.
    """
    outcome = await agent.rank(diagnosis, context)
    if outcome.kind is OutcomeKind.AWAITING_SELECTION:
        outcome = await agent.package(
            outcome.selection_token,
            tenant_id=diagnosis.tenant_id,
            selected_id=outcome.candidates[0]["candidate_id"],
        )
    return outcome.proposal if outcome.kind is OutcomeKind.PROPOSED else None


def _observe_proposal(proposal: ActionProposal | None) -> tuple[bool, bool]:
    """(가드 통과 여부, 스키마 적합 여부) 관측 — 채점 없는 v1 프로세스 지표."""
    if proposal is None:
        return True, True
    survivors = proposal.evidence_metrics.get("candidates", [])
    guard_ok = len(survivors) <= MAX_CANDIDATES
    try:
        ActionProposal.model_validate(proposal.model_dump())
        valid = verify_proposal_hash(proposal)
    except ValidationError:
        valid = False
    return guard_ok, valid


async def run_agent_eval(
    fixture_version: str = "v1",
    agent_factory: Callable[..., RemediationAgent] | None = None,
) -> EvalReport:
    """fixture 진단마다 진짜 agent를 실행해 RegenerationRecord를 생산·채점한다.

    채점은 4-3로 이관됐다(B는 채점 안 함) — 이 하니스는 생성 위임·guard·복구의
    프로세스 지표만 관측한다. tool은 fixture 후보를 통과시키는 결정론 스텁.
    """
    path = FIXTURES_DIR / f"diagnosis_cases_{fixture_version}.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    records: list[RegenerationRecord] = []
    for case in cases:
        diagnosis = DiagnosisResult.model_validate(case["diagnosis"])
        candidates = [
            CreativeCandidate(
                candidate_id=c["candidate_id"],
                # fixture 키 호환: "ad_copy"(구형) 또는 "copy"(현행) 모두 허용.
                copy=c.get("copy") or c.get("ad_copy", ""),
                idx=i,
                # guard asset 규칙(GENERATED_NEW): image_ref가 있어야 통과 — mock s3_key 주입.
                image_ref=c.get("image_ref") or f"s3/{c['candidate_id']}.png",
            )
            for i, c in enumerate(case["candidates"])
        ]
        generator = _CountingGenerator(
            candidates=candidates, fail_times=case.get("generator_fail_times", 0)
        )
        if agent_factory is not None:
            agent = agent_factory(generator=generator)
        else:
            agent = RemediationAgent(
                generator=generator, selection_store=InMemorySelectionRoundStore()
            )
        context = RemediationContext(**_EVAL_CONTEXT_DEFAULTS)

        proposal = await _drive_to_proposal(agent, diagnosis, context)

        guard_ok, valid = _observe_proposal(proposal)
        tool_failures = generator.failures
        recovered = proposal is not None or tool_failures == 0
        records.append(
            RegenerationRecord(
                case_id=case["case_id"],
                baseline_score=case["baseline_score"],
                candidate_scores=(),
                guardrail_passed=guard_ok,
                proposal_valid=valid,
                tool_calls=generator.calls,
                tool_failures=tool_failures,
                recovered=recovered,
                failure_reason=None if recovered else FailureReason.TIMEOUT,
                fixture_version=fixture_version,
            )
        )
    return summarize(records, fixture_version=fixture_version)


# ── 처방 결정 eval — 진단+의향 → action 선택 정확도 (creative 품질과 분리) ──


async def run_action_selection_eval(fixture_version: str = "v1") -> EvalReport:
    """fixture 진단마다 결정 코어(agent의 decide_action)를 돌려 처방 선택을 채점한다.

    creative 후보 생존과 무관하게 '무슨 처방을 골랐나'만 본다 — fixture가 라벨한
    ``expected_action`` 대비 일치율. 의향은 ``risk_appetite`` 노브로 주입(기본 보수적).
    """
    path = FIXTURES_DIR / f"diagnosis_cases_{fixture_version}.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    records: list[RegenerationRecord] = []
    for case in cases:
        if "expected_action" not in case:
            continue  # 라벨 없는 케이스는 처방 채점에서 제외
        diagnosis = DiagnosisResult.model_validate(case["diagnosis"])
        risk = RiskAppetite(case.get("risk_appetite", RiskAppetite.CONSERVATIVE.value))
        chosen = decide_action(diagnosis, risk)
        records.append(
            RegenerationRecord(
                case_id=case["case_id"],
                baseline_score=case["baseline_score"],
                candidate_scores=(),
                guardrail_passed=True,
                expected_action=case["expected_action"],
                chosen_action=chosen,
                action_labeled=True,
                fixture_version=fixture_version,
            )
        )
    return summarize(records, fixture_version=fixture_version)


# ── 기본 tool 체인 실측 — 생성·시뮬·미리보기 구현체를 끝까지 관통 (W3) ──


async def run_default_tools_eval(fixture_version: str = "v1") -> EvalReport:
    """fixture 진단마다 기본 tool 구성(regeneration_tools)으로 agent를 실측한다.

    스텁 하니스(run_agent_eval)와 달리 생성·채점·미리보기 구현체가 실제로 돈다 —
    API 키 없는 환경은 결정론 폴백(Template/Heuristic)으로 같은 결과를 재현한다.
    """
    from domain.management.agents.regeneration_tools import (  # noqa: PLC0415 — 순환 방지
        build_regeneration_agent,
    )

    path = FIXTURES_DIR / f"diagnosis_cases_{fixture_version}.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    agent = build_regeneration_agent()
    records: list[RegenerationRecord] = []
    for case in cases:
        diagnosis = DiagnosisResult.model_validate(case["diagnosis"])
        context = RemediationContext(**_EVAL_CONTEXT_DEFAULTS)
        proposal = await _drive_to_proposal(agent, diagnosis, context)
        guard_ok, valid = _observe_proposal(proposal)
        records.append(
            RegenerationRecord(
                case_id=case["case_id"],
                baseline_score=case["baseline_score"],
                candidate_scores=(),
                guardrail_passed=guard_ok,
                proposal_valid=valid,
                fixture_version=fixture_version,
            )
        )
    return summarize(records, fixture_version=fixture_version)


# ── 에스컬레이션 사다리 eval — 사다리 순서 준수 + 회복 시 정지 (시간축 채점) ──


@dataclass(frozen=True)
class EscalationEvalReport:
    """사다리 1시나리오 채점 — 방문 순서가 우선순위와 일치하고 회복 시 멈췄는가."""

    scenario: str
    visited_actions: tuple[str, ...]
    expected_order: tuple[str, ...]
    order_ok: bool  # 방문 액션이 사다리 우선순위 접두와 일치
    terminal: str  # "recovered" | "exhausted"
    stopped_on_recovery: bool


async def run_escalation_eval(
    *, recover_after: int = 2, max_ticks: int = 8
) -> EscalationEvalReport:
    """데모 시나리오(BID_LOSS)로 사다리를 끝까지 돌려 순서 준수·회복 정지를 채점한다.

    실 agent(결정론 폴백) + 실 detection을 관통한다 — 새 액션(CHANGE_BID_STRATEGY·
    EXPAND_AUDIENCE)이 제안·집행까지 실제로 도는지 시간축으로 확인한다.
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    from domain.management.agents.regeneration_tools import (  # noqa: PLC0415
        build_regeneration_agent,
    )
    from domain.management.contracts.enums import AnomalyType, FaultMode  # noqa: PLC0415
    from domain.management.escalation import (  # noqa: PLC0415
        ACTIVE_LADDERS,
        EscalationController,
        EscalationStatus,
        InMemoryEscalationStore,
    )
    from domain.management.escalation_demo import DemoScenarioDetector  # noqa: PLC0415
    from domain.management.execution.audit_log import InMemoryAuditLog  # noqa: PLC0415

    anomaly = AnomalyType.BID_LOSS
    controller = EscalationController(
        store=InMemoryEscalationStore(),
        detector=DemoScenarioDetector(
            anomaly_fault=FaultMode.BID_LOSS, recover_after=recover_after
        ),
        agent=build_regeneration_agent(),
        audit=InMemoryAuditLog(),
    )
    now = datetime(2026, 6, 12, 9, 0, tzinfo=UTC)
    tenant, account, campaign = "org_eval", "act_eval", "camp_eval_esc"

    visited: list[str] = []
    terminal = "exhausted"
    for _ in range(max_ticks):
        outcome = await controller.re_evaluate(tenant, account, campaign, now=now)
        if outcome.status is EscalationStatus.ESCALATED and outcome.proposal is not None:
            visited.append(outcome.proposal.action_type)
            await controller.on_executed(outcome.run_id, now=now)
        elif outcome.status is EscalationStatus.RECOVERED:
            terminal = "recovered"
            break
        elif outcome.status is EscalationStatus.EXHAUSTED:
            terminal = "exhausted"
            break
        else:
            break

    expected = tuple(ACTIVE_LADDERS.get(anomaly, []))
    order_ok = tuple(visited) == expected[: len(visited)]
    return EscalationEvalReport(
        scenario=f"{anomaly.value}/recover_after={recover_after}",
        visited_actions=tuple(visited),
        expected_order=expected,
        order_ok=order_ok,
        terminal=terminal,
        stopped_on_recovery=(terminal == "recovered"),
    )


def _print_report(title: str, report: EvalReport) -> None:
    print(f"\n── {title} (fixture {report.fixture_version}, {report.total_cases}케이스) ──")
    print(f"  승률(개선율)       {report.win_rate:>6.1%}  (목표 ≥ {WIN_RATE_TARGET:.0%})")
    print(f"  가드레일 통과율    {report.guardrail_pass_rate:>6.1%}")
    print(f"  schema 준수율      {report.schema_compliance_rate:>6.1%}")
    print(f"  tool-call 성공률   {report.tool_call_success_rate:>6.1%}")
    print(f"  도구실패 복구율    {report.tool_failure_recovery_rate:>6.1%}")
    print(f"  처방 선택 정확도   {report.action_selection_accuracy:>6.1%}")
    if report.failure_breakdown:
        print(f"  실패 사유          {report.failure_breakdown}")
    print(f"  목표 충족          {'✅' if report.meets_win_rate_target else '❌'}")


def main() -> None:  # pragma: no cover — 수동 실행 진입점
    """실행: cd backend && uv run python -m domain.management.evals.regeneration_eval"""
    import asyncio  # noqa: PLC0415
    import sys  # noqa: PLC0415

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    _print_report("① 채점 fixture eval", run_eval())
    _print_report("② agent 실행형 eval (스텁 tool)", asyncio.run(run_agent_eval()))
    _print_report("③ agent 실측 eval (기본 tool 체인)", asyncio.run(run_default_tools_eval()))
    _print_report("④ 처방 선택 eval (결정 코어)", asyncio.run(run_action_selection_eval()))

    esc = asyncio.run(run_escalation_eval())
    print(f"\n── ⑤ 에스컬레이션 사다리 eval ({esc.scenario}) ──")
    print(f"  방문 순서          {' → '.join(esc.visited_actions)}")
    print(f"  사다리 순서 준수   {'✅' if esc.order_ok else '❌'}")
    print(f"  종료 / 회복정지    {esc.terminal} / {'✅' if esc.stopped_on_recovery else '❌'}")


if __name__ == "__main__":
    main()
