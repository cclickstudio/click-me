"""🅰 진단 정확도 eval — 주입 고장(정답 라벨) vs 파이프라인 판정.

정답 = "주입한 고장을 맞혔는가"(현실 일치가 아님 — Mock은 테스트 하니스).
오탐률(게이트 #5 ≤5%): 정상 게재를 이상으로 잘못 잡는 비율.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.management.contracts.enums import AnomalyType
from domain.management.contracts.fault_injection import FaultConfig, FaultMode
from domain.management.detection.guardrails import GuardVerdict
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


if __name__ == "__main__":
    r = run()
    gate = "통과" if r.passes_gate5 else "실패"
    print(f"정확도={r.accuracy}  오탐률={r.false_positive_rate}  게이트#5={gate}")
    print(f"케이스={r.n_cases}  평균 tool 호출={r.avg_tool_calls}")
    for label, preds in r.confusion.items():
        print(f"  {label} → {preds}")
