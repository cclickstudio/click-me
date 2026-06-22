# 🅱 재생성 job 서비스 — run_job 상태 매핑 + start + select 멱등
from datetime import UTC, datetime

from domain.management.agents.outcome import OutcomeKind, OutcomeReason, RemediationOutcome
from domain.management.execution.regeneration_jobs import (
    InMemoryRegenerationJobStore,
    JobStatus,
)
from domain.management.execution.service.regeneration_job_service import (
    RegenerationJobService,
)

NOW = datetime(2026, 6, 22, 9, 0, tzinfo=UTC)


class _FakeAgent:
    """rank/package를 미리 정한 outcome으로 대체하는 가짜 RemediationAgent."""

    def __init__(self, rank_outcome=None, package_outcome=None):
        self._rank = rank_outcome
        self._package = package_outcome
        self.rank_calls = 0
        self.package_calls: list[tuple] = []

    async def rank(self, diagnosis, context):
        self.rank_calls += 1
        return self._rank

    async def package(self, token, *, tenant_id, selected_id):
        self.package_calls.append((token, tenant_id, selected_id))
        return self._package


def _service(agent) -> RegenerationJobService:
    return RegenerationJobService(
        store=InMemoryRegenerationJobStore(), agent=agent, clock=lambda: NOW
    )


async def _seed_queued(svc, job_id="job-1", tenant_id="org-1"):
    from domain.management.execution.regeneration_jobs import RegenerationJobRecord

    await svc._store.create(
        RegenerationJobRecord(
            id=job_id,
            tenant_id=tenant_id,
            campaign_id="camp-1",
            status=JobStatus.QUEUED,
            created_at=NOW,
            updated_at=NOW,
        )
    )


async def test_run_job_awaiting_selection_stores_candidates_and_token():
    outcome = RemediationOutcome(
        kind=OutcomeKind.AWAITING_SELECTION,
        selection_token="tok-1",
        candidates=[{"candidate_id": "c1"}, {"candidate_id": "c2"}],
    )
    svc = _service(_FakeAgent(rank_outcome=outcome))
    await _seed_queued(svc)
    await svc.run_job("job-1", diagnosis=None, context=None)
    rec = await svc._store.get("job-1")
    assert rec.status is JobStatus.AWAITING_SELECTION
    assert rec.selection_token == "tok-1"
    assert [c["candidate_id"] for c in rec.candidates] == ["c1", "c2"]
    assert rec.started_at == NOW


async def test_run_job_observe_stores_reason():
    outcome = RemediationOutcome(kind=OutcomeKind.OBSERVE, reason=OutcomeReason.LOW_CONFIDENCE)
    svc = _service(_FakeAgent(rank_outcome=outcome))
    await _seed_queued(svc)
    await svc.run_job("job-1", diagnosis=None, context=None)
    rec = await svc._store.get("job-1")
    assert rec.status is JobStatus.OBSERVE
    assert rec.outcome_reason == OutcomeReason.LOW_CONFIDENCE.value
    assert rec.finished_at == NOW


async def test_run_job_creative_unavailable_stores_reason():
    outcome = RemediationOutcome(
        kind=OutcomeKind.CREATIVE_UNAVAILABLE, reason=OutcomeReason.GENERATOR_EMPTY
    )
    svc = _service(_FakeAgent(rank_outcome=outcome))
    await _seed_queued(svc)
    await svc.run_job("job-1", diagnosis=None, context=None)
    rec = await svc._store.get("job-1")
    assert rec.status is JobStatus.CREATIVE_UNAVAILABLE
    assert rec.outcome_reason == OutcomeReason.GENERATOR_EMPTY.value


async def test_run_job_failed_outcome_marks_failed():
    outcome = RemediationOutcome(kind=OutcomeKind.FAILED)
    svc = _service(_FakeAgent(rank_outcome=outcome))
    await _seed_queued(svc)
    await svc.run_job("job-1", diagnosis=None, context=None)
    rec = await svc._store.get("job-1")
    assert rec.status is JobStatus.FAILED
    assert rec.error


async def test_run_job_swallows_exception_and_marks_failed():
    class _Boom:
        async def rank(self, *a, **k):
            raise RuntimeError("boom")

    svc = _service(_Boom())
    await _seed_queued(svc)
    await svc.run_job("job-1", diagnosis=None, context=None)  # 예외가 새어나오면 실패
    rec = await svc._store.get("job-1")
    assert rec.status is JobStatus.FAILED
    assert "boom" in rec.error


async def test_start_creates_queued_row_and_schedules():
    scheduled: list = []
    svc = RegenerationJobService(
        store=InMemoryRegenerationJobStore(),
        agent=_FakeAgent(),
        clock=lambda: NOW,
        scheduler=lambda coro: scheduled.append(coro),  # create_task 대신 캡처
    )

    class _Dx:
        tenant_id = "org-9"
        campaign_id = "camp-9"

    job_id = await svc.start(_Dx(), context=None)
    rec = await svc._store.get(job_id)
    assert rec is not None
    assert rec.status is JobStatus.QUEUED
    assert rec.tenant_id == "org-9"
    assert rec.campaign_id == "camp-9"
    assert len(scheduled) == 1  # run_job 코루틴이 스케줄됨

    await scheduled[0]  # 캡처한 코루틴을 닫아 RuntimeWarning 방지
