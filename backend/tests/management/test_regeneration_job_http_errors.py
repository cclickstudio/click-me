# 재생성 job 예외 → HTTPException 매핑 (라우터 단위)
import pytest
from fastapi import HTTPException

from api.routers.management import _job_http_error
from domain.management.execution.regeneration_jobs import (
    CandidateNotInJob,
    JobNotAwaitingSelection,
    JobNotFound,
    JobTenantMismatch,
    SelectionContextExpired,
)


@pytest.mark.parametrize(
    "exc,status",
    [
        (JobNotFound("j"), 404),
        (JobTenantMismatch("j"), 404),
        (JobNotAwaitingSelection("j"), 409),
        (SelectionContextExpired("j"), 409),
        (CandidateNotInJob("c"), 422),
    ],
)
def test_job_http_error_maps_status(exc, status):
    result = _job_http_error(exc)
    assert isinstance(result, HTTPException)
    assert result.status_code == status


def test_selection_expired_carries_reason_code():
    result = _job_http_error(SelectionContextExpired("j"))
    assert result.detail["reason"] == "SELECTION_CONTEXT_EXPIRED"
