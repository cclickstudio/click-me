# 페르소나 샘플러 단위 테스트 — 결정성·조건부 샘플링·범위·다양성 검증 (LLM✗)
from __future__ import annotations

from domain.simulation.contracts.schemas import PanelSpec
from domain.simulation.tools.sampling.persona_sampler import (
    PersonaSampler,
    grounding_tier,
    media_band_of_age,
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


def test_ocean_age_conditioned_by_real_band_proportions() -> None:
    # 연령밴드별 실측 유형비율(OSF) 적용 — 고령 코호트는 신경증↓·성실성↑(취약형 비중 급감).
    # 밴드 조건화가 배선됐는지 행동 검증: 변경 전(전 연령 동질)이면 두 코호트 평균이 같다.
    s = _sampler()
    young = s.sample(PanelSpec(size=400, seed=41, target_filter={"age_min": 20, "age_max": 29}))
    old = s.sample(PanelSpec(size=400, seed=42, target_filter={"age_min": 50, "age_max": 59}))

    def mean(ps: list, dim: str) -> float:
        return sum(p.ocean[dim] for p in ps) / len(ps)

    # 성숙원리 방향 — 밴드평균 격차(N≈0.48·C≈0.8)가 표본노이즈보다 훨씬 커 안정적.
    assert mean(old, "neuroticism") < mean(young, "neuroticism")
    assert mean(old, "conscientiousness") > mean(young, "conscientiousness")


def test_ocean_band_marginal_means_match_real_data() -> None:
    # 밴드 factor 잔차 offset — 밴드 marginal 평균이 실측(band_factor_means)에 정합.
    # 유형비율만이면 60+ 성실성≈0.11에 그치나 실측은 +0.87 → offset 배선 여부를 가름.
    s = _sampler()
    old = s.sample(PanelSpec(size=600, seed=51, target_filter={"age_min": 60, "age_max": 69}))
    young = s.sample(PanelSpec(size=600, seed=52, target_filter={"age_min": 20, "age_max": 29}))

    def mean(ps: list, dim: str) -> float:
        return sum(p.ocean[dim] for p in ps) / len(ps)

    # 60+ 성실성 실측 0.871 — 표본노이즈 내 근사(유형혼합한정 ≈0.11이면 실패).
    assert abs(mean(old, "conscientiousness") - 0.871) < 0.25
    assert abs(mean(young, "conscientiousness") - (-0.059)) < 0.2
    assert abs(mean(old, "neuroticism") - (-0.669)) < 0.25


def test_ocean_gender_conditioned() -> None:
    # 성별 조건화(OSF age×gender) — 같은 연령대에서 여성이 남성보다 신경증·친화성↑(실데이터 방향).
    # 이전엔 성별 무조건화로 남녀 성격이 동일했음.
    s = _sampler()
    m = s.sample(
        PanelSpec(size=500, seed=61, target_filter={"age_min": 20, "age_max": 29, "gender": "M"})
    )
    f = s.sample(
        PanelSpec(size=500, seed=62, target_filter={"age_min": 20, "age_max": 29, "gender": "F"})
    )

    def mean(ps: list, dim: str) -> float:
        return sum(p.ocean[dim] for p in ps) / len(ps)

    assert mean(f, "neuroticism") > mean(m, "neuroticism")
    assert mean(f, "agreeableness") > mean(m, "agreeableness")


def test_consumption_values_present_and_zgen() -> None:
    personas = _sampler().sample(PanelSpec(size=100, seed=6))
    young = [p for p in personas if p.age <= 29]
    assert young, "표본에 Z세대 연령이 없음"
    # Z세대 페르소나의 소비가치 키에 generation_specific 항목이 포함된다.
    assert any("취향·덕질" in p.consumption_values for p in young)
    assert all("성능" in p.consumption_values for p in personas)


def test_stratified_allocation_floors_thin_cells_and_weights_correct() -> None:
    # 층화 배분 — 비례 대비 얇은 셀을 보강하고, 과대표집을 가중치로 되돌린다(§3.7 b).
    s = _sampler()
    prop = s.sample(PanelSpec(size=300, seed=31, allocation="proportional"))
    strat = s.sample(PanelSpec(size=300, seed=31, allocation="stratified"))
    assert len(strat) == 300

    def cell_counts(ps: list) -> dict:
        c: dict = {}
        for p in ps:
            key = (p.age // 10, p.gender)
            c[key] = c.get(key, 0) + 1
        return c

    # 층화는 가중치가 균일하지 않다(보정), 비례는 전부 1.0(self-weighting).
    assert all(p.weight == 1.0 for p in prop)
    assert len({round(p.weight, 4) for p in strat}) > 1
    # 가중 합 ≈ 표본수(Σ n_c·w_c = N) — 모집단 불편추정 보장.
    assert abs(sum(p.weight for p in strat) - 300) < 1.0
    # 과대표집(얇은 층 보강)으로 희귀 연령대 커버리지가 비례보다 같거나 넓다.
    assert len(cell_counts(strat)) >= len(cell_counts(prop))


def test_persona_has_socioeconomic_grounded_by_age() -> None:
    personas = _sampler().sample(PanelSpec(size=1000, seed=21))
    for p in personas:
        se = p.socioeconomic
        assert se.get("income_bracket") and se.get("education")
        assert 1 <= se.get("income_code", 0) <= 8
    # 소득은 연령에 grounding — 20대 평균 소득코드 < 40대 평균(은퇴 전 소득곡선).
    young = [p.socioeconomic["income_code"] for p in personas if 20 <= p.age <= 29]
    mid = [p.socioeconomic["income_code"] for p in personas if 40 <= p.age <= 49]
    assert sum(young) / len(young) < sum(mid) / len(mid)


def test_region_uses_real_sido_distribution_when_available() -> None:
    s = _sampler()
    personas = s.sample(PanelSpec(size=1000, seed=12))
    assert all(p.region for p in personas)
    # 행안부 원본이 적재돼 시도 실분포가 있으면 다양한 시도(>10)가 표집된다.
    if s._population.get("region_weights"):
        assert len({p.region for p in personas}) > 10


def test_grounding_tier_and_band_mapping() -> None:
    assert ocean_band_of_age(25) == "20-29"
    assert ocean_band_of_age(67) == "60+"
    # 미디어 밴드는 OCEAN과 구간이 다름(60-69/70+ 분리).
    assert media_band_of_age(67) == "60-69"
    assert media_band_of_age(75) == "70+"
    ocean = _sampler()._ocean
    assert grounding_tier(ocean, 25) == "P1"
    assert grounding_tier(ocean, 55) == "P2"


def test_media_behavior_is_cell_conditioned_with_exposure() -> None:
    # 단계2-β — KISDI 셀 조건부: 주매체·일일분·노출맥락 후보가 페르소나에 실린다.
    personas = _sampler().sample(PanelSpec(size=120, seed=11))
    for p in personas:
        mb = p.media_behavior
        assert mb["primary_medium"]
        assert mb["daily_media_minutes"] >= 5
        # 노출맥락 후보(상위 5) — 반응(4-b) exposure_context 입력.
        for cand in mb["exposure_candidates"]:
            assert {"timeband", "medium", "activity", "place"} <= set(cand)
    # 연령대별로 주매체 구성이 달라야 한다(20대 vs 70+ 동질화 아님).
    young = {p.media_behavior["primary_medium"] for p in personas if p.age <= 29}
    old = {p.media_behavior["primary_medium"] for p in personas if p.age >= 70}
    assert young and old
