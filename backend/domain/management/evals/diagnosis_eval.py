"""🅰 진단 정확도 eval — 주입 고장(정답 라벨) vs 파이프라인 판정.

정답 = "주입한 고장을 맞혔는가"(현실 일치가 아님 — Mock은 테스트 하니스).
오탐률(게이트 #5 ≤5%): 정상 게재를 이상으로 잘못 잡는 비율.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from domain.management.contracts.enums import AnomalyType, DiagnosisStatus, RelevanceRank
from domain.management.contracts.fault_injection import FaultConfig, FaultMode
from domain.management.contracts.schemas import RelevanceDiagnostics
from domain.management.detection.guardrails import GuardVerdict
from domain.management.detection.performance_dx import diagnose_performance
from domain.management.detection.service.detection_service import run_detection_for_fault

# 주입 FaultMode → 기대 AnomalyType (1:1 정답 라벨)
FAULT_TO_LABEL: dict[FaultMode, AnomalyType] = {
    FaultMode.BID_LOSS: AnomalyType.BID_LOSS,
    FaultMode.REVIEW_REJECTED: AnomalyType.REVIEW_REJECTED,
    FaultMode.REVIEW_DELAY: AnomalyType.REVIEW_DELAY,
    FaultMode.AUDIENCE_TOO_NARROW: AnomalyType.AUDIENCE_TOO_NARROW,
    FaultMode.QUALITY_DEGRADED: AnomalyType.QUALITY_DEGRADED,
}


@dataclass
class DiagnosisEvalResult:
    accuracy: float
    false_positive_rate: float
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    avg_tool_calls: float = 0.0
    n_cases: int = 0

    @property
    def passes_gate5(self) -> bool:
        return self.false_positive_rate <= 0.05


def run(seeds: range = range(20)) -> DiagnosisEvalResult:
    """각 고장모드 × 시드로 진단을 돌려 정확도/혼동행렬/오탐률을 측정한다."""
    correct = 0
    total = 0
    tool_calls = 0
    confusion: dict[str, dict[str, int]] = {}

    for seed in seeds:
        for fault_mode, expected in FAULT_TO_LABEL.items():
            dx, _ = run_detection_for_fault(FaultConfig(mode=fault_mode), seed=seed)
            predicted = dx.anomaly_type.value if dx else "none"
            confusion.setdefault(expected.value, {}).setdefault(predicted, 0)
            confusion[expected.value][predicted] += 1
            total += 1
            if dx and dx.anomaly_type == expected:
                correct += 1
            if dx:
                tool_calls += len(dx.evidence_metrics.get("agent_tool_calls", []))

    # 오탐률 — 정상 게재(고장 없음)를 이상으로 잡는 비율
    fp = 0
    fp_total = 0
    for seed in seeds:
        dx, guard = run_detection_for_fault(None, seed=seed)
        fp_total += 1
        if guard == GuardVerdict.DELIVERY_ANOMALY:
            fp += 1

    return DiagnosisEvalResult(
        accuracy=round(correct / total, 3) if total else 0.0,
        false_positive_rate=round(fp / fp_total, 3) if fp_total else 0.0,
        confusion=confusion,
        avg_tool_calls=round(tool_calls / total, 2) if total else 0.0,
        n_cases=total,
    )


@dataclass
class PerformanceEvalResult:
    """성과 미달(PERFORMANCE_BELOW_TARGET) 판정 정확도 — 실데이터 축(고장 주입 무관)."""

    accuracy: float
    false_alarms: int  # 정상(목표 70% 이내)을 미달로 잘못 잡은 수
    n_cases: int

    @property
    def passes(self) -> bool:
        return self.false_alarms == 0 and self.accuracy >= 0.99


def _relevance(conv: RelevanceRank) -> RelevanceDiagnostics:
    return RelevanceDiagnostics(
        campaign_id="camp_perf",
        conversion_rate_ranking=conv,
        as_of=datetime.now(UTC),
    )


# 합성 케이스 — (roas, target_roas, conv_rank, 기대 결과). 기대: anomaly_type 또는 None(정상).
# below_average + 미달 → CONFIRMED, average + 미달 → INCONCLUSIVE, 70% 이내 → None(오탐 금지).
_PERF_CASES = [
    (1.0, 3.0, RelevanceRank.BELOW_AVERAGE_20, AnomalyType.PERFORMANCE_BELOW_TARGET),
    (1.5, 3.0, RelevanceRank.AVERAGE, AnomalyType.PERFORMANCE_BELOW_TARGET),
    (2.5, 3.0, RelevanceRank.AVERAGE, None),  # 83% — 목표 70% 이내라 정상
    (3.5, 3.0, RelevanceRank.ABOVE_AVERAGE, None),  # 목표 초과 — 정상
    (None, 3.0, RelevanceRank.UNKNOWN, None),  # ROAS 측정 불가 — 판정 불가(정직)
    (1.0, None, RelevanceRank.BELOW_AVERAGE_10, None),  # 목표 미입력 — 판정 불가
]


def run_performance() -> PerformanceEvalResult:
    """성과 미달 진단을 합성 케이스로 채점 — 결정론, 키·LLM 불필요(게이트 #9)."""
    correct = 0
    false_alarms = 0
    now = datetime.now(UTC)
    for roas, target, conv_rank, expected in _PERF_CASES:
        dx = diagnose_performance(
            "org_eval",
            "camp_perf",
            roas=roas,
            target_roas=target,
            as_of=now,
            relevance=_relevance(conv_rank),
        )
        predicted = dx.anomaly_type if dx else None
        if predicted == expected:
            correct += 1
        if expected is None and dx is not None:
            false_alarms += 1
        # CONFIRMED vs INCONCLUSIVE 분기 검증 — below_average는 CONFIRMED여야 한다.
        if dx is not None and conv_rank in {
            RelevanceRank.BELOW_AVERAGE_10,
            RelevanceRank.BELOW_AVERAGE_20,
            RelevanceRank.BELOW_AVERAGE_35,
        }:
            assert dx.status == DiagnosisStatus.CONFIRMED  # noqa: S101 — eval 단정
    n = len(_PERF_CASES)
    return PerformanceEvalResult(
        accuracy=round(correct / n, 3) if n else 0.0,
        false_alarms=false_alarms,
        n_cases=n,
    )


if __name__ == "__main__":
    r = run()
    gate = "통과" if r.passes_gate5 else "실패"
    print(f"[게재 고장] 정확도={r.accuracy}  오탐률={r.false_positive_rate}  게이트#5={gate}")
    print(f"  케이스={r.n_cases}  평균 tool 호출={r.avg_tool_calls}")
    for label, preds in r.confusion.items():
        print(f"  {label} → {preds}")
    p = run_performance()
    verdict = "통과" if p.passes else "실패"
    print(f"[성과 미달] 정확도={p.accuracy}  오탐={p.false_alarms}  판정={verdict}")
