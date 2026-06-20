"""🅰 진단 agent — INCONCLUSIVE 케이스 전용 ReAct(결정론 코어).

LLM 모델·temperature 고정값은 R&R P6 미합의(빈칸)이므로 결정론 추론 코어로 구현한다
(데모는 API 키 없이 재현 — 게이트 #9). 실제 LLM 드롭인 지점은 _reason()으로 격리.
read-tool은 evidence_metrics + 전달된 시계열 범위 내에서만 사용(정보 방화벽, R&R §2.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from domain.management.contracts.enums import AnomalyType, DiagnosisSource, DiagnosisStatus
from domain.management.contracts.schemas import DiagnosisResult, MetricsSnapshot

MAX_TOOL_CALLS = 6  # R&R P6 [안]: 1회 진단당 tool 호출 상한 (초과 시 INCONCLUSIVE 반환)


@dataclass
class AgentTrace:
    """ReAct 추적 — diagnosis_eval의 'tool 사용 효과' 측정 대상."""

    tool_calls: list[str] = field(default_factory=list)

    def call(self, name: str) -> None:
        self.tool_calls.append(name)


def run_diagnosis_agent(
    prior: DiagnosisResult,
    snapshots: list[MetricsSnapshot],
    expected: list[float],
    anomaly_hours: list[int],
) -> DiagnosisResult:
    """결정론 규칙이 못 가른 케이스를 추가 신호로 재판정한다."""
    trace = AgentTrace()
    window = [snapshots[h] for h in anomaly_hours]

    # tool 1: ctr 추세 (앞/뒤 절반 비교) — 품질 저하 신호
    trace.call("read_metrics.ctr_trend")
    ctr_slope = _trend([s.ctr for s in window])

    # tool 2: frequency 추세 — 피로/포화 신호
    trace.call("read_metrics.frequency_trend")
    freq_last = window[-1].frequency if window else 1.0

    # tool 3: 노출 공백 패턴 — 시간대 간헐 결손
    trace.call("read_history.impression_gaps")
    gaps = _intermittent_gaps(expected, [s.impressions for s in snapshots])

    anomaly, status, confidence, hypothesis = _reason(
        ctr_slope, freq_last, gaps, len(trace.tool_calls)
    )

    return DiagnosisResult(
        diagnosis_id=f"dx_{uuid4().hex[:8]}",
        tenant_id=prior.tenant_id,
        campaign_id=prior.campaign_id,
        anomaly_type=anomaly,
        source=DiagnosisSource.AGENT,
        hypothesis=hypothesis,
        confidence=confidence,
        evidence_metrics={
            **prior.evidence_metrics,
            "agent_tool_calls": trace.tool_calls,
            "ctr_slope": ctr_slope,
            "intermittent_gaps": gaps,
        },
        metrics_as_of=prior.metrics_as_of,
        status=status,
    )


def _reason(
    ctr_slope: float, freq_last: float, gaps: int, tool_calls: int
) -> tuple[AnomalyType, DiagnosisStatus, float, str]:
    """추론 코어 — 실제 LLM으로 교체 가능한 단일 지점."""
    if tool_calls > MAX_TOOL_CALLS:
        return (
            AnomalyType.SCHEDULE_GAP,
            DiagnosisStatus.INCONCLUSIVE,
            0.4,
            "tool 호출 상한 초과 — 판정 보류(INCONCLUSIVE).",
        )
    if ctr_slope < -0.0003:
        return (
            AnomalyType.QUALITY_DEGRADED,
            DiagnosisStatus.CONFIRMED,
            0.82,
            f"이상 구간 ctr 지속 하락(slope={ctr_slope:.5f}) — 크리에이티브 품질 저하로 판정.",
        )
    if gaps >= 2:
        return (
            AnomalyType.SCHEDULE_GAP,
            DiagnosisStatus.CONFIRMED,
            0.78,
            f"비피크 시간대 {gaps}곳 노출 공백 — 게재 일정 문제로 판정.",
        )
    if freq_last >= 2.5:
        return (
            AnomalyType.AUDIENCE_TOO_NARROW,
            DiagnosisStatus.CONFIRMED,
            0.7,
            f"빈도 {freq_last} 누적 상승 — 도달 포화(타겟 협소)로 판정.",
        )
    return (
        AnomalyType.LEARNING_PHASE,
        DiagnosisStatus.INCONCLUSIVE,
        0.5,
        "뚜렷한 단일 원인 미검출 — 학습 단계 가능성, 추가 관측 필요(INCONCLUSIVE).",
    )


def _trend(values: list[float]) -> float:
    """앞 절반 평균 → 뒤 절반 평균의 변화량(시간당 근사 기울기)."""
    if len(values) < 2:
        return 0.0
    mid = len(values) // 2
    head = sum(values[:mid]) / mid
    tail = sum(values[mid:]) / (len(values) - mid)
    return round((tail - head) / max(1, len(values) // 2), 6)


def _intermittent_gaps(expected: list[float], observed: list[int]) -> int:
    """비피크(기대>0)인데 관측이 거의 0인 시간대 수 — 단, 연속 구간이 아닌 산발."""
    return sum(
        1 for exp, obs in zip(expected, observed, strict=True) if exp > 1 and obs < exp * 0.1
    )
