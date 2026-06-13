# 페르소나 샘플러 단위 테스트 — 결정성·조건부 샘플링·범위·다양성 검증 (LLM✗)
from __future__ import annotations

from domain.simulation.contracts.schemas import PanelSpec
from domain.simulation.tools.sampling.persona_sampler import (
    PersonaSampler,
    grounding_tier,
    ocean_band_of_age,
)


def _sampler() -> PersonaSampler:
    return PersonaSampler()


def test_deterministic_same_seed() -> None:
    s = _sampler()
    a = s.sample(PanelSpec(size=50, seed=7))
    b = s.sample(PanelSpec(size=50, seed=7))
    assert [p.model_dump() for p in a] == [p.model_dump() for p in b]


def test_size_and_min_age_respected() -> None:
    personas = _sampler().sample(PanelSpec(size=200, seed=1))
    assert len(personas) == 200
    assert all(p.age >= 14 for p in personas)


def test_age_diversity_not_homogenized() -> None:
    personas = _sampler().sample(PanelSpec(size=200, seed=2))
    ages = {p.age for p in personas}
    genders = {p.gender for p in personas}
    assert len(ages) > 20  # 다양성은 데이터가 강제(원칙 2)
    assert genders == {"M", "F"}


def test_target_filter_gender() -> None:
    personas = _sampler().sample(PanelSpec(size=100, seed=3, target_filter={"gender": "F"}))
    assert all(p.gender == "F" for p in personas)


def test_target_filter_age_range_conditional() -> None:
    spec = PanelSpec(size=100, seed=4, target_filter={"age_min": 20, "age_max": 29})
    personas = _sampler().sample(spec)
    assert all(20 <= p.age <= 29 for p in personas)
    # Layer1 스킵 금지 — 20대 안에서도 세부 연령 실분포 유지(균등 단일값 아님).
    assert len({p.age for p in personas}) >= 8


def test_ocean_factor_scores_in_range() -> None:
    personas = _sampler().sample(PanelSpec(size=80, seed=5))
    for p in personas:
        assert set(p.ocean) == {
            "openness",
            "conscientiousness",
            "extraversion",
            "agreeableness",
            "neuroticism",
        }
        # factor score(표준화) — 안전 클립 범위 내.
        assert all(-5.0 <= v <= 5.0 for v in p.ocean.values())


def test_consumption_values_present_and_zgen() -> None:
    personas = _sampler().sample(PanelSpec(size=100, seed=6))
    young = [p for p in personas if p.age <= 29]
    assert young, "표본에 Z세대 연령이 없음"
    # Z세대 페르소나의 소비가치 키에 generation_specific 항목이 포함된다.
    assert any("취향·덕질" in p.consumption_values for p in young)
    assert all("성능" in p.consumption_values for p in personas)


def test_grounding_tier_and_band_mapping() -> None:
    assert ocean_band_of_age(25) == "20-29"
    assert ocean_band_of_age(67) == "60+"
    ocean = _sampler()._ocean
    assert grounding_tier(ocean, 25) == "P1"
    assert grounding_tier(ocean, 55) == "P2"
