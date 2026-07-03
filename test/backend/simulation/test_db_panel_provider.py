# DB 패널 조회 어댑터 단위 테스트 — 히트(부분집합 반환)/미스(폴백 위임) 둘 다 LLM✗
from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from domain.simulation import models
from domain.simulation.contracts.schemas import PanelSpec
from domain.simulation.repositories.panel_repository import PanelRepository
from domain.simulation.tools.panel.db_provider import DbPanelProvider
from domain.simulation.tools.sampling.persona_sampler import PersonaSampler


async def _sessionmaker() -> async_sessionmaker:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(models.SimBase.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


class _StubFallback:
    """DB 미스 시 위임되는 자리 — 호출 여부만 확인하면 되므로 고정 결과 반환."""

    def __init__(self) -> None:
        self.called = False

    async def get_or_build(self, spec: PanelSpec) -> tuple[str, list]:
        self.called = True
        return "fallback-version", []


async def test_db_panel_provider_miss_delegates_to_fallback() -> None:
    sm = await _sessionmaker()
    fallback = _StubFallback()
    provider = DbPanelProvider(sm, fallback=fallback)

    version, personas = await provider.get_or_build(PanelSpec(version="panel-v1", size=5))

    assert fallback.called is True
    assert version == "fallback-version"
    assert personas == []


async def test_db_panel_provider_hit_returns_filtered_subset() -> None:
    sm = await _sessionmaker()
    base_personas = PersonaSampler().sample(PanelSpec(size=50, seed=7))
    async with sm() as session:
        await PanelRepository(session).create(
            version="panel-v1",
            seed=7,
            size=50,
            model_version="mock-narrator-0",
            grounding_meta={},
            personas=base_personas,
        )
        await session.commit()

    fallback = _StubFallback()
    provider = DbPanelProvider(sm, fallback=fallback)

    version, subset = await provider.get_or_build(
        PanelSpec(version="panel-v1", size=999, target_filter={"gender": "F"})
    )

    assert fallback.called is False  # DB 히트 — 폴백 미호출
    assert version == "panel-v1"
    assert subset  # 부분집합 존재
    assert all(p.gender == "F" for p in subset)


async def test_db_panel_provider_caps_to_requested_size_deterministically() -> None:
    # 필터 통과분이 요청 표본보다 많으면 size만큼 결정적 서브샘플 — 초과 LLM 콜(비용) 방지.
    sm = await _sessionmaker()
    base_personas = PersonaSampler().sample(PanelSpec(size=60, seed=9))
    async with sm() as session:
        await PanelRepository(session).create(
            version="panel-v1",
            seed=9,
            size=60,
            model_version="mock-narrator-0",
            grounding_meta={},
            personas=base_personas,
        )
        await session.commit()

    provider = DbPanelProvider(sm, fallback=_StubFallback())
    spec = PanelSpec(version="panel-v1", size=5, seed=3)

    _, first = await provider.get_or_build(spec)
    _, second = await provider.get_or_build(spec)

    assert len(first) == 5  # 60명 중 요청한 5명만
    assert [p.persona_id for p in first] == [p.persona_id for p in second]  # 같은 spec → 재현
