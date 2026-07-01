# 리포지토리 단위 테스트 — SQLite(aiosqlite) 인메모리로 9테이블 영속화 라운드트립 검증
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from domain.simulation import models
from domain.simulation.contracts.enums import EmotionTag
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    Aisas,
    PanelSpec,
    PersonaReaction,
    RubricScore,
    SimulationAggregate,
)
from domain.simulation.repositories.panel_repository import PanelRepository
from domain.simulation.repositories.simulation_repository import SimulationRepository
from domain.simulation.tools.sampling.persona_sampler import PersonaSampler


async def _make_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(models.SimBase.metadata.create_all)
    return AsyncSession(engine)


async def test_panel_repository_roundtrip() -> None:
    session = await _make_session()
    async with session:
        personas = PersonaSampler().sample(PanelSpec(size=5, seed=1))
        repo = PanelRepository(session)
        panel_id, id_map = await repo.create(
            version="panel-v1",
            seed=1,
            size=5,
            model_version="mock-narrator-0",
            grounding_meta={"population": "real"},
            personas=personas,
        )
        await session.commit()

        panel = await repo.get(panel_id)
        assert panel is not None and panel.status == "READY" and panel.size == 5
        assert len(id_map) == 5
        n = await session.scalar(
            select(func.count())
            .select_from(models.Persona)
            .where(models.Persona.panel_id == panel_id)
        )
        assert n == 5


async def test_simulation_repository_saves_full_run() -> None:
    session = await _make_session()
    async with session:
        personas = PersonaSampler().sample(PanelSpec(size=6, seed=2))
        panel_id, id_map = await PanelRepository(session).create(
            version="panel-v1",
            seed=2,
            size=6,
            model_version="mock",
            grounding_meta={},
            personas=personas,
        )

        reactions = [
            PersonaReaction(
                persona_id=p.persona_id,
                aisas=Aisas(attention=True, action=(i % 2 == 0)),
                purchase_intent=3,
                trust=4,
                emotion_tag=EmotionTag.CURIOSITY,
                qa_passed=True,
            )
            for i, p in enumerate(personas)
        ]
        rubric = [RubricScore(dimension="clarity", score=70, evidence={"mock": True})]
        aggregate = SimulationAggregate(
            click_intent_rate=0.5,
            ci_low=0.3,
            ci_high=0.7,
            purchase_intent=3.0,
            trust_avg=4.0,
            rejection_rate=0.0,
            engine_version="agg-1",
        )
        ad = AdInterpretation(ad_id=str(uuid.uuid4()), detected_industry="beverage")

        repo = SimulationRepository(session)
        sim_id = await repo.save_run(
            ad_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            panel_id=panel_id,
            target_filter=None,
            target_mode="AUTO",
            sample_size=6,
            ad=ad,
            reactions=reactions,
            rubric=rubric,
            aggregate=aggregate,
            persona_uuid_by_ref=id_map,
        )
        await session.commit()

        sim = await repo.get(sim_id)
        assert sim is not None and sim.status == "COMPLETED" and sim.qa_passed_count == 6

        n_react = await session.scalar(
            select(func.count())
            .select_from(models.PersonaReaction)
            .where(models.PersonaReaction.simulation_id == sim_id)
        )
        assert n_react == 6
        n_agg = await session.scalar(
            select(func.count())
            .select_from(models.SimulationAggregate)
            .where(models.SimulationAggregate.simulation_id == sim_id)
        )
        assert n_agg == 1
