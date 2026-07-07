# 패널 빌더·캐시·로드 단위 테스트 — 결정적 스텁 나레이터(LLM✗)로 검증
from __future__ import annotations

from domain.simulation.contracts.schemas import PanelSpec
from domain.simulation.tools.panel.builder import (
    CachedPanelProvider,
    PanelBuilder,
    filter_personas,
    load_panel,
    save_panel,
)
from domain.simulation.tools.sampling.persona_sampler import PersonaSampler


class _StubNarrator:
    """결정적 서사 스텁 — LLM 없이 패널 빌더 로직만 검증(mock 어댑터 제거됨)."""

    version = "stub-narrator-0"

    def narrate(self, persona) -> str:
        return f"{persona.age}세 {persona.gender} · {persona.region}."


def _builder() -> PanelBuilder:
    return PanelBuilder(sampler=PersonaSampler(), narrator=_StubNarrator())


def test_build_fills_narrative_for_all() -> None:
    panel = _builder().build(PanelSpec(size=30, seed=1))
    assert panel["size"] == 30
    assert panel["narrator"] == "stub-narrator-0"
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


def test_filter_personas_by_persona_id_ignores_age_gender() -> None:
    """Individual 모드 페르소나 지정 선택 — persona_id 있으면 그 1명만, age/gender는 무시."""
    panel = _builder().build(PanelSpec(size=20, seed=7))
    from domain.simulation.contracts.schemas import Persona

    personas = [Persona(**d) for d in panel["personas"]]
    target = personas[3]
    result = filter_personas(
        personas, {"persona_id": target.persona_id, "gender": "그럴리없음", "age_min": 999}
    )
    assert result == [target]


def test_filter_personas_by_unknown_persona_id_returns_empty() -> None:
    panel = _builder().build(PanelSpec(size=10, seed=8))
    from domain.simulation.contracts.schemas import Persona

    personas = [Persona(**d) for d in panel["personas"]]
    assert filter_personas(personas, {"persona_id": "P_없음"}) == []
