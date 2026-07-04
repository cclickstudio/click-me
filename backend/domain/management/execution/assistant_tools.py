# 🅱 어시스턴트 tool-body — 채팅 그래프(🅰)가 @tool로 래핑할 위임 함수들
"""숫자·상태는 여기서(실측·DB) 나온다. 어시스턴트는 예외를 던지지 않고 dict로 표면화한다."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.management.execution.audit_log import AuditSink


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
