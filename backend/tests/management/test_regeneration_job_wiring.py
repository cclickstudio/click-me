# 🅱 재생성 job wiring — 싱글톤 service + use_mock store 분기
import pytest

from domain.management import wiring
from domain.management.execution.db_stores import DbRegenerationJobStore
from domain.management.execution.regeneration_jobs import InMemoryRegenerationJobStore
from domain.management.execution.service.regeneration_job_service import (
    RegenerationJobService,
)
from domain.management.wiring import (
    build_regeneration_job_service,
    build_regeneration_job_store,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    # 모듈 전역 싱글톤이 다른 테스트로 새지 않게 매 테스트 전후 초기화.
    wiring._regeneration_job_service = None
    yield
    wiring._regeneration_job_service = None


class _Settings:
    use_mock = True


class _RealSettings:
    use_mock = False


def test_store_is_inmemory_when_mock():
    store = build_regeneration_job_store(_Settings())
    assert isinstance(store, InMemoryRegenerationJobStore)


def test_store_is_db_when_not_mock():
    store = build_regeneration_job_store(_RealSettings())
    assert isinstance(store, DbRegenerationJobStore)


def test_service_is_singleton():
    a = build_regeneration_job_service(_Settings())
    b = build_regeneration_job_service(_Settings())
    assert isinstance(a, RegenerationJobService)
    assert a is b  # 같은 인스턴스(_pending 보존)
