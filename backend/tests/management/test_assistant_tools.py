# 🅱 어시스턴트 tool-body — job 서비스/audit에 위임하는 dict 반환 함수
from datetime import UTC, datetime

from domain.management.execution.assistant_tools import (
    check_regeneration,
    execution_history,
)
from domain.management.execution.audit_log import AuditEvent, InMemoryAuditLog
from domain.management.execution.regeneration_jobs import (
    InMemoryRegenerationJobStore,
    JobStatus,
    RegenerationJobRecord,
)
from domain.management.execution.service.regeneration_job_service import (
    RegenerationJobService,
)

NOW = datetime(2026, 6, 22, 9, 0, tzinfo=UTC)


async def test_check_regeneration_awaiting_returns_candidates():
    store = InMemoryRegenerationJobStore()
    await store.create(
        RegenerationJobRecord(
            id="job-1",
            tenant_id="org-1",
            campaign_id="camp-1",
            status=JobStatus.AWAITING_SELECTION,
            created_at=NOW,
            updated_at=NOW,
            candidates=[{"candidate_id": "c1"}],
        )
    )
    svc = RegenerationJobService(store=store, agent=None, clock=lambda: NOW)
    out = await check_regeneration(svc, "job-1", tenant_id="org-1")
    assert out["status"] == "awaiting_selection"
    assert out["candidates"] == [{"candidate_id": "c1"}]


async def test_check_regeneration_other_tenant_returns_error_not_raise():
    store = InMemoryRegenerationJobStore()
    await store.create(
        RegenerationJobRecord(
            id="job-1",
            tenant_id="org-1",
            campaign_id="camp-1",
            status=JobStatus.RUNNING,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    svc = RegenerationJobService(store=store, agent=None, clock=lambda: NOW)
    out = await check_regeneration(svc, "job-1", tenant_id="org-OTHER")
    assert out["error"] == "not_found"  # 어시스턴트는 예외 대신 표면화


async def test_execution_history_filters_by_tenant():
    log = InMemoryAuditLog()
    await log.append(AuditEvent(category="executor.completed", tenant_id="org-1", approval_id="a1"))
    await log.append(AuditEvent(category="executor.completed", tenant_id="org-2", approval_id="a2"))
    out = await execution_history(log, tenant_id="org-1")
    assert out["count"] == 1
    assert out["events"][0]["approval_id"] == "a1"
    assert out["events"][0]["category"] == "executor.completed"
