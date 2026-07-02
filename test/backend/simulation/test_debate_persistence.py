# 토론 영속화 통합 테스트 — DebateService 완료 토론이 3테이블에 저장되는지 SQLite로 검증
#
# persona_debates / persona_debate_participants / persona_debate_utterances 저장 + 미주입 시 생략.
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from core.db import Base
from core.models import PersonaDebate, PersonaDebateParticipant, PersonaDebateUtterance
from domain.simulation.adapters.memory_store import InMemorySimulationStore
from domain.simulation.adapters.mock_debate import MockDebater, MockJudge
from domain.simulation.repositories.debate_repository import DebateRepository
from domain.simulation.service.debate_service import DebateService
from domain.simulation.tools.debate.loader import load_all_dummies

# core.models 토론 테이블은 PG 전용 JSONB를 쓴다(운영은 Neon). SQLite에서만 TEXT로 렌더해
# 이 테스트가 DB 없이도 매핑·저장 흐름을 검증하게 한다(운영 코드 무변경, 테스트 한정 shim).
# @compiles는 타입 클래스에 전역 등록 — create_all(런타임) 시점에만 적용되므로 import 순서 무관.


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # noqa: ANN001, ANN202
    return "TEXT"


def _engine_and_sessionmaker():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _service(store, persistence=None) -> DebateService:
    return DebateService(
        store=store,
        debater_factory=lambda rs: MockDebater(rs),
        judge=MockJudge(),
        persistence=persistence,
    )


async def test_completed_debate_is_persisted_to_db() -> None:
    engine, sm = _engine_and_sessionmaker()
    # 토론 3테이블만 생성(core Base 메타데이터). simulation_id는 ORM상 FK 미선언이라 독립 저장 가능.
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                PersonaDebate.__table__,
                PersonaDebateParticipant.__table__,
                PersonaDebateUtterance.__table__,
            ],
        )
    try:
        dummy = load_all_dummies()[0]
        sim_id = str(uuid.uuid4())
        store = InMemorySimulationStore()
        svc = _service(store, persistence=DebateRepository(sm))

        result = await svc.run(dummy.reactions, dummy.ad_analysis, simulation_id=sim_id)
        assert result is not None and result["debate_id"]  # 저장 후 debate_id 병기
        debate = result["debate"]
        debate_id = uuid.UUID(result["debate_id"])

        async with sm() as session:
            row = await session.get(PersonaDebate, debate_id)
            assert row is not None and row.status == "COMPLETED"
            assert str(row.simulation_id) == sim_id
            assert row.rounds_run == debate["rounds_run"]

            n_part = await session.scalar(
                select(func.count())
                .select_from(PersonaDebateParticipant)
                .where(PersonaDebateParticipant.debate_id == debate_id)
            )
            assert n_part == len(debate["participants"])

            n_utt = await session.scalar(
                select(func.count())
                .select_from(PersonaDebateUtterance)
                .where(PersonaDebateUtterance.debate_id == debate_id)
            )
            total_utt = sum(len(p["utterances"]) for p in debate["participants"])
            assert n_utt == total_utt

            # 발언이 participant FK로 연결됐다(고아 utterance 없음).
            n_orphan = await session.scalar(
                select(func.count())
                .select_from(PersonaDebateUtterance)
                .where(PersonaDebateUtterance.participant_id.is_(None))
            )
            assert n_orphan == 0
    finally:
        await engine.dispose()


async def test_no_persistence_without_simulation_id() -> None:
    # simulation_id 미지정 — FK 충족 불가라 토론 저장 생략, 런은 정상 완료(debate_id None).
    engine, sm = _engine_and_sessionmaker()
    try:
        dummy = load_all_dummies()[0]
        store = InMemorySimulationStore()
        svc = _service(store, persistence=DebateRepository(sm))
        result = await svc.run(dummy.reactions, dummy.ad_analysis)  # simulation_id 없음
        assert result is not None and result["debate_id"] is None
    finally:
        await engine.dispose()
