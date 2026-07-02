# 외부 marginal raking + OCEAN→행동 경량 조건화 테스트 (작업2)
from __future__ import annotations

import random

from domain.simulation.contracts.schemas import PanelSpec
from domain.simulation.tools.sampling.persona_sampler import (
    PersonaSampler,
    _media_minutes_factor,
    media_band_of_age,
)
from domain.simulation.tools.sampling.raking import rake_weights


def test_rake_weights_matches_one_dim_target() -> None:
    rows = ["A", "A", "A", "B"]  # 3:1 → 목표 0.5:0.5
    w = rake_weights(rows, [(lambda r: r, {"A": 0.5, "B": 0.5})])
    assert abs(sum(w) - 4) < 1e-6  # 가중합=행수(평균 1.0)
    a = sum(wi for wi, r in zip(w, rows, strict=True) if r == "A")
    b = sum(wi for wi, r in zip(w, rows, strict=True) if r == "B")
    assert abs(a - 2.0) < 1e-3 and abs(b - 2.0) < 1e-3


def test_rake_weights_two_dims_converge() -> None:
    rows = [("M", "Y"), ("M", "O"), ("F", "Y"), ("F", "O"), ("F", "O")]
    w = rake_weights(
        rows,
        [(lambda r: r[0], {"M": 0.5, "F": 0.5}), (lambda r: r[1], {"Y": 0.5, "O": 0.5})],
    )
    n = len(rows)
    male = sum(wi for wi, r in zip(w, rows, strict=True) if r[0] == "M")
    young = sum(wi for wi, r in zip(w, rows, strict=True) if r[1] == "Y")
    assert abs(male - n * 0.5) < 1e-2
    assert abs(young - n * 0.5) < 1e-2


def test_rake_empty_rows() -> None:
    assert rake_weights([], [(lambda r: r, {"A": 1.0})]) == []


def test_ocean_conditions_consumption_rate() -> None:
    s = PersonaSampler()
    hi = {"conscientiousness": 2.0, "openness": 0.0, "extraversion": 0.0}
    lo = {"conscientiousness": -2.0, "openness": 0.0, "extraversion": 0.0}

    def share(ocean: dict, key: str, n: int = 400) -> float:
        return sum(s._sample_consumption(random.Random(i), 35, ocean)[key] for i in range(n)) / n

    # 성실성↑이면 성능 중시 보유율↑(경량 조건화 방향).
    assert share(hi, "성능") > share(lo, "성능")


def test_ocean_conditions_media_minutes_factor() -> None:
    assert _media_minutes_factor({"openness": 2.0, "extraversion": 2.0}) > 1.0
    assert _media_minutes_factor({"openness": -2.0, "extraversion": -2.0}) < 1.0
    assert _media_minutes_factor({}) == 1.0  # 데이터 없으면 1.0(무변화)


def test_census_raking_default_off_preserves_weights() -> None:
    # 기본(OFF)은 비례추출 가중 1.0 그대로 — 회귀 보존.
    personas = PersonaSampler().sample(PanelSpec(size=200, seed=5))
    assert all(p.weight == 1.0 for p in personas)


def test_census_raking_aligns_gender_marginal() -> None:
    # rake_to_census=True면 도달성 과표집 후에도 가중 성별 marginal이 census에 정합.
    s = PersonaSampler(reachability_sampling=True, rake_to_census=True)
    personas = s.sample(PanelSpec(size=400, seed=5))
    bands = s._population["bands"]
    male_target = sum(b["share"] * b.get("male_ratio", 0.5) for b in bands)
    total = sum(p.weight for p in personas)
    wmale = sum(p.weight for p in personas if p.gender == "M") / total
    assert abs(wmale - male_target) < 0.03
    # 가중합 ≈ 표본수(평균 1.0).
    assert abs(total - len(personas)) < 1.0
    assert media_band_of_age(25) == "20-29"  # 밴드 매핑 정합 확인
