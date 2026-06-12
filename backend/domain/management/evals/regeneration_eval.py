"""🅱 재생성 품질 eval — 승률·가드레일 통과율·tool-call 성공률·schema 준수율·복구율.

목표: 재생성 개선율(승률) ≥ 70% (PRD §5.2). 점수 보고 시 픽스처 버전 병기 (§9.0).
픽스처: ``evals/fixtures/regeneration/cases_<버전>.json`` — 🅱 광고 케이스.
단서: 시뮬 점수 ↔ 실제 성과 상관 미검증 — 발표에서 정직하게 공개 (§7).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from domain.management.agents.regeneration import (
    BANNED_EXPRESSIONS,
    MAX_CANDIDATES,
    CreativeCandidate,
    RegenerationAgent,
    RegenerationContext,
)
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


def failure_breakdown(records: Sequence[RegenerationRecord]) -> dict[str, int]:
    counter = Counter(str(r.failure_reason) for r in records if r.failure_reason is not None)
    return dict(counter)


def summarize(records: Sequence[RegenerationRecord], fixture_version: str = "v1") -> EvalReport:
    rate = win_rate(records)
    return EvalReport(
        fixture_version=fixture_version,
        total_cases=len(records),
        win_rate=rate,
        guardrail_pass_rate=guardrail_pass_rate(records),
        schema_compliance_rate=schema_compliance_rate(records),
        tool_call_success_rate=tool_call_success_rate(records),
        tool_failure_recovery_rate=tool_failure_recovery_rate(records),
        failure_breakdown=failure_breakdown(records),
        meets_win_rate_target=rate >= WIN_RATE_TARGET,
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


# ── agent 실행형 하니스 — 진짜 RegenerationAgent를 fixture 진단에 돌려 채점 ──


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


@dataclass
class _CountingScorer:
    """결정론 시뮬 점수 tool 스텁 — fail_ids 후보는 매 호출 실패(폴백 유도)."""

    scores: dict[str, float]
    fail_ids: set[str] = field(default_factory=set)
    calls: int = 0
    failures: int = 0

    async def score(self, candidate: CreativeCandidate) -> float:
        self.calls += 1
        if candidate.candidate_id in self.fail_ids:
            self.failures += 1
            raise TimeoutError("시뮬 tool 고장 주입")
        return self.scores[candidate.candidate_id]


_EVAL_CONTEXT_DEFAULTS = {
    "ad_account_id": "act_eval",
    "target_object_ids": ("camp-eval-1",),
    "budget_before_krw": 50_000,
    "budget_after_krw": 50_000,
    "run_days": 7,
    "expected_state_version": "sv-eval",
    "approval_policy_version": "approval-policy-v1",
    "action_type": "replace_creative",
}


def _score_proposal(
    proposal: ActionProposal | None, banned_ids: set[str]
) -> tuple[tuple[float, ...], bool, bool]:
    """(후보 점수들, 가드 통과 여부, 스키마 적합 여부) 관측."""
    if proposal is None:
        return (), True, True
    evidence = proposal.evidence_metrics["candidates"]
    scores = tuple(c["sim_score"] for c in evidence)
    survivor_ids = {c["candidate_id"] for c in evidence}
    guard_ok = not (banned_ids & survivor_ids) and len(evidence) <= MAX_CANDIDATES
    try:
        ActionProposal.model_validate(proposal.model_dump())
        valid = verify_proposal_hash(proposal)
    except ValidationError:
        valid = False
    return scores, guard_ok, valid


async def run_agent_eval(
    fixture_version: str = "v1",
    agent_factory: Callable[..., RegenerationAgent] | None = None,
) -> EvalReport:
    """fixture 진단마다 진짜 agent를 실행해 RegenerationRecord를 생산·채점한다.

    tool은 fixture가 정의한 결정론 스텁 — 실제 생성·시뮬 tool이 확정되면
    ``agent_factory`` 주입으로 교체한다 (개선율 ≥70%는 그때부터 실측).
    """
    path = FIXTURES_DIR / f"diagnosis_cases_{fixture_version}.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    records: list[RegenerationRecord] = []
    for case in cases:
        diagnosis = DiagnosisResult.model_validate(case["diagnosis"])
        candidates = [
            CreativeCandidate(candidate_id=c["candidate_id"], ad_copy=c["ad_copy"])
            for c in case["candidates"]
        ]
        generator = _CountingGenerator(
            candidates=candidates, fail_times=case.get("generator_fail_times", 0)
        )
        scorer = _CountingScorer(
            scores={c["candidate_id"]: c["score"] for c in case["candidates"]},
            fail_ids=set(case.get("scorer_fail_ids", [])),
        )
        if agent_factory is not None:
            agent = agent_factory(generator=generator, scorer=scorer)
        else:
            agent = RegenerationAgent(generator=generator, scorer=scorer)
        context = RegenerationContext(**_EVAL_CONTEXT_DEFAULTS)

        proposal = await agent.propose(diagnosis, context)

        banned_ids = {
            c["candidate_id"]
            for c in case["candidates"]
            if any(banned in c["ad_copy"] for banned in BANNED_EXPRESSIONS)
        }
        scores, guard_ok, valid = _score_proposal(proposal, banned_ids)
        tool_failures = generator.failures + scorer.failures
        recovered = proposal is not None or tool_failures == 0
        records.append(
            RegenerationRecord(
                case_id=case["case_id"],
                baseline_score=case["baseline_score"],
                candidate_scores=scores,
                guardrail_passed=guard_ok,
                proposal_valid=valid,
                tool_calls=generator.calls + scorer.calls,
                tool_failures=tool_failures,
                recovered=recovered,
                failure_reason=None if recovered else FailureReason.TIMEOUT,
                fixture_version=fixture_version,
            )
        )
    return summarize(records, fixture_version=fixture_version)
