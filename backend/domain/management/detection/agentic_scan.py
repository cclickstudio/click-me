# 캠페인 성과 진단 공유 함수 — 규칙(결정론) → 애매하면 에이전트 재판정. 라우터·워커 공용.
"""성과 미달 진단의 단일 진실원.

결정론 `diagnose_performance`로 1차 판정하고, INCONCLUSIVE면 `build_diagnosis_agent`
(LLM ReAct, use_mock/키없음이면 passthrough)로 재판정한다. 임계 수치는 policy 정본을
쓰는 diagnose_performance에 위임 — 이 함수는 종합·재판정만 한다(휴리스틱 금지).

라우터(`/anomaly/scan`·캠페인 상세)와 APScheduler 워커가 같은 진단을 공유하려고 도메인에 둔다.
additive·best-effort: 신호 조회나 LLM이 실패해도 None 반환(호출부 화면·스캔을 막지 않음).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langsmith import traceable

from domain.management.contracts.enums import DiagnosisStatus
from domain.management.detection.performance_dx import diagnose_performance

if TYPE_CHECKING:
    from datetime import datetime


@traceable(name="management.performance_diagnosis", run_type="chain", tags=["management"])
async def diagnose_campaign(
    reader, settings, campaign_id: str, summary: dict, as_of: datetime
) -> dict | None:
    """성과 미달 진단 — 결정론 판정 후 INCONCLUSIVE면 LLM agent 재판정(키 있을 때).

    None이면 이상 없음(또는 진단 실패) — 호출부는 그대로 진행한다.
    """
    # 지연 import — wiring(무거운 조립)·demo와의 import 순환 방지(scheduler.py와 동일 패턴).
    from domain.management.demo import TENANT_ID  # noqa: PLC0415
    from domain.management.wiring import build_diagnosis_agent  # noqa: PLC0415

    try:
        relevance = await reader.get_relevance_diagnostics(campaign_id)
        dx = diagnose_performance(
            TENANT_ID,
            campaign_id,
            roas=summary.get("roas"),
            target_roas=summary.get("target_roas"),
            as_of=as_of,
            relevance=relevance,
        )
        if dx is None:
            return None
        if dx.status == DiagnosisStatus.INCONCLUSIVE:
            dx = await build_diagnosis_agent(settings)(dx, reader)
    except Exception:  # noqa: BLE001 — 진단은 부가 정보: 실패해도 실데이터 상세는 무영향
        return None
    return {
        "anomaly_type": dx.anomaly_type.value,
        "hypothesis": dx.hypothesis,
        "confidence": dx.confidence,
        "source": dx.source.value,
        "status": dx.status.value,
    }
