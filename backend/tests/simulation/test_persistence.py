# 영속화 통합 테스트 — SimulationService 완료 런이 9테이블에 저장되는지 SQLite로 검증
from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from domain.simulation import models
from domain.simulation.contracts.schemas import SimulationRunRequest
from domain.simulation.repositories.persistence import _as_uuid
from domain.simulation.wiring import build_simulation_service


def _engine_and_sessionmaker():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _wait_done(svc, run_id: str) -> None:
    for _ in range(400):
        if svc._store.get_status(run_id) in ("COMPLETED", "FAILED"):
            return
        await asyncio.sleep(0.02)


async def test_completed_run_is_persisted_to_db() -> None:
    engine, sm = _engine_and_sessionmaker()
    async with engine.begin() as conn:
        await conn.run_sync(models.SimBase.metadata.create_all)
    try:
        svc = build_simulation_service(session_factory=sm)
        run_id = await svc.start(SimulationRunRequest(ad_id="AD-1024", sample_size=8))
        await _wait_done(svc, run_id)

        result = svc.get_result(run_id)
        assert result is not None and "simulation_id" in result  # DB 저장 후 id 병기
        sim_id = _as_uuid(result["simulation_id"])

        async with sm() as session:
            sim = await session.get(models.Simulation, sim_id)
            assert sim is not None and sim.status == "COMPLETED"
            # 반응·집계 행이 실제로 저장됐다.
            n_react = await session.scalar(
                select(func.count())
                .select_from(models.PersonaReaction)
                .where(models.PersonaReaction.simulation_id == sim_id)
            )
            assert n_react == len(result["reactions"])
            n_agg = await session.scalar(
                select(func.count())
                .select_from(models.SimulationAggregate)
                .where(models.SimulationAggregate.simulation_id == sim_id)
            )
            assert n_agg == 1
            # 패널·페르소나도 저장됐다(반응의 persona FK 충족).
            n_persona = await session.scalar(select(func.count()).select_from(models.Persona))
            assert n_persona == sim.sample_size
    finally:
        await engine.dispose()  # aiosqlite 연결 스레드 정리(루프 종료 hang 방지)


async def test_no_persistence_when_session_factory_absent() -> None:
    # session_factory 미주입(.env 없는 기본 경로) — DB 저장 생략, 런은 정상 완료.
    svc = build_simulation_service()
    run_id = await svc.start(SimulationRunRequest(ad_id="AD-1", sample_size=5))
    await _wait_done(svc, run_id)
    result = svc.get_result(run_id)
    assert result is not None and "simulation_id" not in result
    assert svc._store.get_status(run_id) == "COMPLETED"


def test_as_uuid_handles_non_uuid_and_uuid() -> None:
    import uuid

    valid = str(uuid.uuid4())
    assert str(_as_uuid(valid)) == valid  # 이미 UUID면 보존
    a = _as_uuid("AD-1024")
    assert a == _as_uuid("AD-1024") and a != _as_uuid("AD-9999")  # 결정적·구분됨
