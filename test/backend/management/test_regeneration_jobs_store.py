# 🅱 재생성 job store 단위 테스트 — 상태 레코드 + 인메모리 CRUD
from datetime import UTC, datetime

import pytest

from domain.management.execution.regeneration_jobs import (
    InMemoryRegenerationJobStore,
    JobStatus,
    RegenerationJobRecord,
)

NOW = datetime(2026, 6, 22, 9, 0, tzinfo=UTC)


def _record(job_id: str = "job-1", tenant_id: str = "org-1") -> RegenerationJobRecord:
    return RegenerationJobRecord(
        id=job_id,
        tenant_id=tenant_id,
        campaign_id="camp-1",
        status=JobStatus.QUEUED,
        created_at=NOW,
        updated_at=NOW,
    )


async def test_create_then_get_returns_same_record():
    store = InMemoryRegenerationJobStore()
    await store.create(_record())
    got = await store.get("job-1")
    assert got is not None
    assert got.id == "job-1"
    assert got.status is JobStatus.QUEUED


async def test_get_missing_returns_none():
    store = InMemoryRegenerationJobStore()
    assert await store.get("nope") is None


async def test_save_persists_mutation():
    store = InMemoryRegenerationJobStore()
    rec = _record()
    await store.create(rec)
    rec.status = JobStatus.RUNNING
    rec.started_at = NOW
    await store.save(rec)
    got = await store.get("job-1")
    assert got.status is JobStatus.RUNNING
    assert got.started_at == NOW


async def test_get_returns_copy_not_live_reference():
    # store가 내부 객체를 그대로 노출하면 호출자가 저장 없이 상태를 바꿔버릴 수 있다.
    store = InMemoryRegenerationJobStore()
    await store.create(_record())
    got = await store.get("job-1")
    got.status = JobStatus.FAILED
    again = await store.get("job-1")
    assert again.status is JobStatus.QUEUED


def test_naive_datetime_rejected():
    # UTC-aware 강제 (naive 금지 — management/CLAUDE.md 공통 규칙).
    with pytest.raises(ValueError, match="UTC-aware"):
        RegenerationJobRecord(
            id="job-1",
            tenant_id="org-1",
            campaign_id="camp-1",
            status=JobStatus.QUEUED,
            created_at=datetime(2026, 6, 22, 9, 0),  # naive
            updated_at=NOW,
        )
