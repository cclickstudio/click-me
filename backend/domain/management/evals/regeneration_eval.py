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

from domain.management.contracts.enums import FailureReason

if TYPE_CHECKING:
    from collections.abc import Sequence

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
