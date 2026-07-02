# 성과 미달 진단 — 실 캠페인 ROAS가 고객 목표에 못 미치는지 결정론으로 판정한다.
"""성과 부진(PERFORMANCE_BELOW_TARGET) 진단 — 게재 고장(deterministic_dx)과 다른 축.

게재 고장은 '왜 광고가 안 나가나'(노출 곡선)이고, 이건 '나가는데 목표 미달인가'(실데이터·
고객 목표)다. target_check.is_target_missed로 미달 여부를 가르고, 메타 채점표
(conversion_rate_ranking)로 확신도·가설을 보강한다. 신호가 명확하면 CONFIRMED,
모호하면 INCONCLUSIVE → 진단 agent로 라우팅(06-20 멘토 피드백 §3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from langsmith import traceable

from domain.management.contracts.enums import (
    AnomalyType,
    DiagnosisSource,
    DiagnosisStatus,
    RelevanceRank,
)
from domain.management.contracts.schemas import DiagnosisResult
from domain.management.target_check import is_target_missed

if TYPE_CHECKING:
    from datetime import datetime

    from domain.management.contracts.schemas import RelevanceDiagnostics

#: '평균 이하' 등급 — 전환 경쟁력 저조의 결정적 단서 (meta-data-sources §2②).
_BELOW_AVERAGE: frozenset[RelevanceRank] = frozenset(
    {
        RelevanceRank.BELOW_AVERAGE_10,
        RelevanceRank.BELOW_AVERAGE_20,
        RelevanceRank.BELOW_AVERAGE_35,
    }
)


@traceable(
    name="management:diagnose_performance", run_type="chain", tags=["management", "detection"]
)
def diagnose_performance(
    tenant_id: str,
    campaign_id: str,
    *,
    roas: float | None,
    target_roas: float | None,
    as_of: datetime,
    relevance: RelevanceDiagnostics | None = None,
) -> DiagnosisResult | None:
    """목표 미달이면 DiagnosisResult, 정상이면 None.

    roas는 실측·추정 어느 쪽이어도 된다(management의 _real_summary가 산출한 값). 미달이
    명확하고 메타 전환율 순위가 평균 이하면 CONFIRMED, 단일 원인 불명이면 INCONCLUSIVE.
    """
    if not is_target_missed(roas, target_roas):
        return None
    # is_target_missed True면 roas·target_roas 둘 다 not None·target_roas>0 보장.
    assert roas is not None and target_roas  # noqa: S101 — 계약 명시(타입 좁히기)
    miss_pct = roas / target_roas * 100
    evidence: dict[str, object] = {
        "roas": round(roas, 3),
        "target_roas": target_roas,
        "miss_ratio": round(roas / target_roas, 3),
    }
    conv_rank = relevance.conversion_rate_ranking if relevance else RelevanceRank.UNKNOWN
    if relevance is not None:
        evidence["conversion_rate_ranking"] = conv_rank.value

    if conv_rank in _BELOW_AVERAGE:
        return _result(
            tenant_id,
            campaign_id,
            as_of,
            hypothesis=(
                f"실 ROAS가 목표의 {miss_pct:.0f}% — 전환율 순위 {conv_rank.value}(평균 이하)로 "
                "전환 경쟁력 저조."
            ),
            confidence=0.8,
            evidence=evidence,
            status=DiagnosisStatus.CONFIRMED,
        )
    return _result(
        tenant_id,
        campaign_id,
        as_of,
        hypothesis=f"실 ROAS가 목표의 {miss_pct:.0f}%로 미달 — 단일 원인 미검출(추가 분석 필요).",
        confidence=0.5,
        evidence=evidence,
        status=DiagnosisStatus.INCONCLUSIVE,
    )


def _result(
    tenant_id: str,
    campaign_id: str,
    as_of: datetime,
    *,
    hypothesis: str,
    confidence: float,
    evidence: dict[str, object],
    status: DiagnosisStatus,
) -> DiagnosisResult:
    return DiagnosisResult(
        diagnosis_id=f"perf_{uuid4().hex[:8]}",
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        anomaly_type=AnomalyType.PERFORMANCE_BELOW_TARGET,
        source=DiagnosisSource.DETERMINISTIC,
        hypothesis=hypothesis,
        confidence=confidence,
        evidence_metrics=evidence,
        metrics_as_of=as_of,
        status=status,
    )
