# 패널 빌더·캐시·로드 단위 테스트 — MockNarrator(결정적, LLM✗)로 검증
from __future__ import annotations

from domain.simulation.adapters.mock_engine import MockNarrator
from domain.simulation.contracts.schemas import PanelSpec
from domain.simulation.panel.builder import (
    CachedPanelProvider,
    PanelBuilder,
    filter_personas,
    load_panel,
    save_panel,
)
from domain.simulation.sampling.persona_sampler import PersonaSampler


def _builder() -> PanelBuilder:
    return PanelBuilder(sampler=PersonaSampler(), narrator=MockNarrator())


def test_build_fills_narrative_for_all() -> None:
    panel = _builder().build(PanelSpec(size=30, seed=1))
    assert panel["size"] == 30
    assert panel["narrator"] == "mock-narrator-0"
    assert all(p["profile_narrative"] for p in panel["personas"])


def test_build_qa_drops_empty_narrative() -> None:
    class _SilentNarrator:
        version = "silent"

        def narrate(self, persona) -> str:
            return ""  # 전부 QA 탈락

    builder = PanelBuilder(sampler=PersonaSampler(), narrator=_SilentNarrator())
    panel = builder.build(PanelSpec(size=10, seed=2))
    assert panel["size"] == 0
    assert panel["dropped_qa"] == 10


def test_save_load_roundtrip(tmp_path) -> None:
    panel = _builder().build(PanelSpec(size=20, seed=3))
    path = save_panel(panel, tmp_path / "panel-v1.json")
    loaded = load_panel(path)
    assert loaded["personas"] == panel["personas"]


async def test_cached_provider_loads_without_regen(tmp_path) -> None:
    panel = _builder().build(PanelSpec(size=40, seed=4))
    path = save_panel(panel, tmp_path / "panel-v1.json")

    provider = CachedPanelProvider(path)
    version, personas = await provider.get_or_build(PanelSpec(size=999, seed=99))
    # 요청 size·seed 와 무관하게 캐시된 패널을 그대로 반환(재생성✗).
    assert version == "panel-v1"
    assert len(personas) == 40
    assert all(p.profile_narrative for p in personas)


async def test_cached_provider_target_filter_subset(tmp_path) -> None:
    panel = _builder().build(PanelSpec(size=100, seed=5))
    path = save_panel(panel, tmp_path / "panel-v1.json")
    provider = CachedPanelProvider(path)
    _, females = await provider.get_or_build(
        PanelSpec(size=100, seed=5, target_filter={"gender": "F", "age_min": 20, "age_max": 39})
    )
    assert females  # 부분집합 존재
    assert all(p.gender == "F" and 20 <= p.age <= 39 for p in females)


def test_filter_personas_helper() -> None:
    panel = _builder().build(PanelSpec(size=60, seed=6))
    from domain.simulation.contracts.schemas import Persona

    personas = [Persona(**d) for d in panel["personas"]]
    males = filter_personas(personas, {"gender": "M"})
    assert all(p.gender == "M" for p in males)
