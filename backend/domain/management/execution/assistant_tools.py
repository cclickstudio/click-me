# 🅱 어시스턴트 tool-body — 채팅 그래프(🅰)가 @tool로 래핑할 위임 함수들
"""숫자·상태는 여기서(실측·DB) 나온다. 어시스턴트는 예외를 던지지 않고 dict로 표면화한다.
start_regeneration은 이미 만들어진 DiagnosisResult를 받는 오케스트레이터에서 호출된다 —
detection(🅰) 호출은 이 모듈이 하지 않는다(설계 §1 경계).

연결 대기 — 🅰가 build_management_agent에서 @tool로 래핑 후 INTENT_TOOLS에 등록(설계 §3·§5.1).
현재는 라우터 엔드포인트로만 노출되며 채팅 그래프에서는 아직 호출되지 않는다."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.management.execution.regeneration_jobs import (
    JobNotFound,
    JobTenantMismatch,
)

if TYPE_CHECKING:
    from domain.management.execution.audit_log import AuditSink
    from domain.management.execution.service.regeneration_job_service import (
        RegenerationJobService,
    )


async def start_regeneration(service: RegenerationJobService, diagnosis: Any, context: Any) -> dict:
    """재생성 비동기 job 시작 → {job_id, status:"queued"} 즉답. 무거운 생성은 백그라운드."""
    job_id = await service.start(diagnosis, context)
    return {"job_id": job_id, "status": "queued"}


async def check_regeneration(
    service: RegenerationJobService, job_id: str, *, tenant_id: str
) -> dict:
    """job 진행 상태 조회. AWAITING_SELECTION이면 후보 목록 포함."""
    try:
        rec = await service.get(job_id, tenant_id=tenant_id)
    except (JobNotFound, JobTenantMismatch):
        return {"error": "not_found"}
    out: dict[str, Any] = {"job_id": rec.id, "status": rec.status.value}
    if rec.candidates:
        out["candidates"] = rec.candidates
    if rec.proposal:
        out["proposal"] = rec.proposal
    if rec.outcome_reason:
        out["outcome_reason"] = rec.outcome_reason
    return out


async def execution_history(audit: AuditSink, *, tenant_id: str, limit: int = 20) -> dict:
    """테넌트의 최근 실행 감사 이벤트 요약(읽기). org 스코프 강제.

    v1은 테넌트 단위. 캠페인 정밀 필터는 감사 이벤트에 campaign_id가 실린 뒤 후속(설계 §5.3).
    """
    events = await audit.for_tenant(tenant_id)
    rows = [
        {
            "category": e.category,
            "approval_id": e.approval_id,
            "occurred_at": e.occurred_at.isoformat(),
        }
        for e in events[-limit:]
    ]
    return {"count": len(rows), "events": rows}
