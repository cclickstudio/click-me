# 감사 로그 테넌트 단위 조회 — execution_history 토대
from domain.management.execution.audit_log import AuditEvent, InMemoryAuditLog


async def test_for_tenant_returns_only_that_tenant_in_time_order():
    log = InMemoryAuditLog()
    await log.append(AuditEvent(category="executor.completed", tenant_id="org-1", approval_id="a1"))
    await log.append(AuditEvent(category="executor.completed", tenant_id="org-2", approval_id="a2"))
    await log.append(AuditEvent(category="executor.rejected", tenant_id="org-1", approval_id="a3"))
    events = await log.for_tenant("org-1")
    assert [e.approval_id for e in events] == ["a1", "a3"]
    assert all(e.tenant_id == "org-1" for e in events)


async def test_for_tenant_empty_when_none_match():
    log = InMemoryAuditLog()
    await log.append(AuditEvent(category="x", tenant_id="org-1"))
    assert await log.for_tenant("org-zzz") == ()
