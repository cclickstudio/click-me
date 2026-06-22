# 🅱 재생성 job wiring — 싱글톤 service + use_mock store 분기
from domain.management.execution.regeneration_jobs import InMemoryRegenerationJobStore
from domain.management.execution.service.regeneration_job_service import (
    RegenerationJobService,
)
from domain.management.wiring import (
    build_regeneration_job_service,
    build_regeneration_job_store,
)


class _Settings:
    use_mock = True


def test_store_is_inmemory_when_mock():
    store = build_regeneration_job_store(_Settings())
    assert isinstance(store, InMemoryRegenerationJobStore)


def test_service_is_singleton():
    a = build_regeneration_job_service(_Settings())
    b = build_regeneration_job_service(_Settings())
    assert isinstance(a, RegenerationJobService)
    assert a is b  # 같은 인스턴스(_pending 보존)
