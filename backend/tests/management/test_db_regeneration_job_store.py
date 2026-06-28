# 🅱 DB 재생성 job store — Protocol 준수 + record↔row 변환 (라이브 DB 불필요한 단위 검증)
from datetime import UTC, datetime

from core.models import RegenerationJobRow
from domain.management.execution.db_stores import DbRegenerationJobStore, _row_to_record
from domain.management.execution.regeneration_jobs import JobStatus, RegenerationJobStore

NOW = datetime(2026, 6, 22, 9, 0, tzinfo=UTC)


def test_db_store_satisfies_protocol():
    store: RegenerationJobStore = DbRegenerationJobStore()
    assert hasattr(store, "create") and hasattr(store, "get") and hasattr(store, "save")


def test_row_to_record_maps_fields():
    row = RegenerationJobRow(
        id="job-1",
        tenant_id="org-1",
        campaign_id="camp-1",
        status="awaiting_selection",
        selection_token="tok-1",
        candidates=[{"candidate_id": "c1"}],
        created_at=NOW,
        updated_at=NOW,
    )
    rec = _row_to_record(row)
    assert rec.id == "job-1"
    assert rec.status is JobStatus.AWAITING_SELECTION
    assert rec.candidates == [{"candidate_id": "c1"}]


def test_row_to_record_null_candidates_maps_to_empty_list():
    # 레거시 NULL 또는 빈 후보 → InMemory store와 동일하게 [](never None)으로 복원.
    row = RegenerationJobRow(
        id="job-2",
        tenant_id="org-1",
        campaign_id="camp-1",
        status="queued",
        candidates=None,
        created_at=NOW,
        updated_at=NOW,
    )
    rec = _row_to_record(row)
    assert rec.candidates == []
