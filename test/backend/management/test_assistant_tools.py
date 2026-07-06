# 🅱 어시스턴트 tool-body — audit에 위임하는 dict 반환 함수
from domain.management.execution.assistant_tools import execution_history
from domain.management.execution.audit_log import AuditEvent, InMemoryAuditLog


async def test_execution_history_filters_by_tenant():
    log = InMemoryAuditLog()
    await log.append(AuditEvent(category="executor.completed", tenant_id="org-1", approval_id="a1"))
    await log.append(AuditEvent(category="executor.completed", tenant_id="org-2", approval_id="a2"))
    out = await execution_history(log, tenant_id="org-1")
    assert out["count"] == 1
    assert out["events"][0]["approval_id"] == "a1"
    assert out["events"][0]["category"] == "executor.completed"
