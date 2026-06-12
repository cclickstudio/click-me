"""🅰 결정론 진단 — 심사·일정·예산·학습 (규칙엔진).

규칙으로 판정 가능한 경우 confidence=1.0의 CONFIRMED를 반환하고,
규칙으로 못 가르는 경우 INCONCLUSIVE를 반환해 진단 agent로 라우팅한다.
"""

from uuid import uuid4

from domain.management.contracts.enums import AnomalyType, DiagnosisSource, DiagnosisStatus
from domain.management.contracts.policy import CPM_ANCHOR_KRW
from domain.management.contracts.schemas import DiagnosisResult, MetricsSnapshot

# BID_LOSS 판정 임계 (meta-data-sources.md §5 신호 매핑)
_CPM_SURGE_RATIO = 1.3
_FREQUENCY_FATIGUE = 3.0


def diagnose(
    tenant_id: str,
    campaign_id: str,
    snapshots: list[MetricsSnapshot],
    expected: list[float],
    anomaly_hours: list[int],
) -> DiagnosisResult:
    """이상 구간의 신호 조합으로 AnomalyType을 결정론 판정한다."""
    window = [snapshots[h] for h in anomaly_hours]
    expected_window = sum(expected[h] for h in anomaly_hours)
    observed_window = sum(s.impressions for s in window)
    cpm_avg = sum(s.cpm_krw for s in window) / len(window)
    spend_total = sum(s.spend_krw for s in snapshots)
    last = snapshots[-1]

    # 정보 방화벽 — 이후 추론(agent 포함)은 이 스냅샷 밖의 정보를 쓰지 않는다
    evidence = {
        "anomaly_hours": anomaly_hours,
        "impressions_expected": int(expected_window),
        "impressions_observed": observed_window,
        "deficit_ratio": round(observed_window / expected_window, 3),
        "cpm_window_avg_krw": int(cpm_avg),
        "cpm_anchor_krw": CPM_ANCHOR_KRW,
        "cpm_surge_ratio": round(cpm_avg / CPM_ANCHOR_KRW, 2),
        "spend_total_krw": spend_total,
        "frequency_last": last.frequency,
    }

    if observed_window == 0:
        anomaly, status, confidence = AnomalyType.REVIEW_REJECTED, DiagnosisStatus.CONFIRMED, 1.0
        hypothesis = "이상 구간 전체 노출 0 — 심사 거절(DISAPPROVED)로 게재가 중단된 것으로 판정."
    elif cpm_avg >= CPM_ANCHOR_KRW * _CPM_SURGE_RATIO:
        anomaly, status, confidence = AnomalyType.BID_LOSS, DiagnosisStatus.CONFIRMED, 1.0
        hypothesis = (
            f"경매 입찰 패배 — {anomaly_hours[0]}시 이후 CPM이 앵커 대비 "
            f"{evidence['cpm_surge_ratio']}배로 급등했고 예산이 남는데도 노출이 "
            f"기대 대비 {int(evidence['deficit_ratio'] * 100)}% 수준으로 급감."
        )
    elif last.frequency >= _FREQUENCY_FATIGUE:
        anomaly, status, confidence = (
            AnomalyType.AUDIENCE_TOO_NARROW,
            DiagnosisStatus.CONFIRMED,
            1.0,
        )
        hypothesis = f"빈도 {last.frequency} — 타겟 모수가 좁아 도달이 조기 포화된 것으로 판정."
    else:
        anomaly, status, confidence = AnomalyType.SCHEDULE_GAP, DiagnosisStatus.INCONCLUSIVE, 0.4
        hypothesis = "결정론 규칙으로 판정 불가 — 진단 agent로 라우팅."

    return DiagnosisResult(
        diagnosis_id=f"dx_{uuid4().hex[:8]}",
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        anomaly_type=anomaly,
        source=DiagnosisSource.DETERMINISTIC,
        hypothesis=hypothesis,
        confidence=confidence,
        evidence_metrics=evidence,
        metrics_as_of=last.as_of,
        status=status,
    )
