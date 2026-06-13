# 페르소나 속성 샘플러 — 단계1~3을 통계 분포에서 샘플링 (LLM✗, 동질화 방어 1차 방어선)
#
# 단계1 인구(연령×성별, target_filter 조건부) → 2-α OCEAN(연령조건) → 2-β 행동(stub) → 3 소비가치.
# 서사(4-a)는 여기서 만들지 않는다(profile_narrative=""). 결정적(spec.seed) — 고정 패널 재현용.
# 분포가 placeholder/실데이터 무엇이든 동일 코드로 동작. data_status()로 grounding 상태 확인.
from __future__ import annotations

import random
from typing import Any

from domain.simulation.contracts.schemas import PanelSpec, Persona
from domain.simulation.data import loader

# 지역 분포 미확보 → 근사 가중치(행안부 지역 CSV 확보 시 교체). 합=1.0.
_REGION_WEIGHTS: dict[str, float] = {
    "서울": 0.18,
    "경기": 0.26,
    "인천": 0.06,
    "부산": 0.06,
    "대구": 0.05,
    "대전": 0.03,
    "광주": 0.03,
    "기타": 0.33,
}

# OCEAN 데이터 하한(논문 표본 14세부터) — 기본 샘플은 이 이상만.
_MIN_AGE = 14
_OPEN_BAND_TOP = 84  # "60+"/"70+" 같은 개방 구간의 상한 캡.
_OCEAN_CLIP = (-5.0, 5.0)  # factor score(표준화) 안전 클립.
_Z_GEN_MAX_AGE = 29  # Z세대 근사(2026년 기준 대략) — 소비가치 generation_specific 적용 범위.


def _band_range(band: str) -> tuple[int, int]:
    band = band.strip()
    if band.endswith("+"):
        return int(band[:-1]), _OPEN_BAND_TOP
    lo, hi = band.split("-")
    return int(lo), int(hi)


def ocean_band_of_age(age: int) -> str:
    """실제 나이를 OCEAN 연령밴드로 매핑."""
    if age < 20:
        return "14-19"
    if age >= 60:
        return "60+"
    return f"{age // 10 * 10}-{age // 10 * 10 + 9}"


def grounding_tier(ocean: dict[str, Any], age: int) -> str:
    """연령 grounding 신뢰도 — 20~30대 P1, 그 외 P2(표본 제한)."""
    band = ocean_band_of_age(age)
    return ocean["age_bands"].get(band, {}).get("tier", "P2")


def _weighted_choice(rng: random.Random, items: list[tuple[Any, float]]) -> Any:
    total = sum(w for _, w in items)
    r = rng.random() * total
    upto = 0.0
    for value, w in items:
        upto += w
        if r <= upto:
            return value
    return items[-1][0]


class PersonaSampler:
    """분포에서 페르소나 속성 묶음을 샘플링. MockPanelProvider 와 동일한 get_or_build 시그니처."""

    def __init__(
        self,
        *,
        population: dict | None = None,
        ocean: dict | None = None,
        consumption: dict | None = None,
        min_age: int = _MIN_AGE,
    ) -> None:
        self._population = population or loader.load_population_age_sex()
        self._ocean = ocean or loader.load_ocean_age_bands()
        self._consumption = consumption or loader.load_consumption_values()
        self._min_age = min_age

    async def get_or_build(self, spec: PanelSpec) -> tuple[str, list[Persona]]:
        return spec.version, self.sample(spec)

    def sample(self, spec: PanelSpec) -> list[Persona]:
        rng = random.Random(spec.seed)
        cells = self._population_cells(spec.target_filter)
        if not cells:
            raise ValueError("target_filter 가 모든 인구 셀을 제외했습니다.")
        regions = list(_REGION_WEIGHTS.items())

        personas: list[Persona] = []
        for i in range(spec.size):
            (band_lo, band_hi, sex) = _weighted_choice(rng, cells)
            age = rng.randint(band_lo, band_hi)
            personas.append(
                Persona(
                    persona_id=f"P-{i:05d}",
                    age=age,
                    gender=sex,
                    region=_weighted_choice(rng, regions),
                    ocean=self._sample_ocean(rng, age),
                    media_behavior=self._sample_media(rng),
                    consumption_values=self._sample_consumption(rng, age),
                    profile_narrative="",  # 4-a(LLM)에서 채움 — P3
                )
            )
        return personas

    def _population_cells(
        self, target_filter: dict | None
    ) -> list[tuple[tuple[int, int, str], float]]:
        """연령밴드×성별 셀 목록. target_filter(age_min/age_max/gender)로 조건부 필터·재가중.

        Layer1 스킵 금지 — 필터 안에서도 실분포(밴드 share·성비)를 유지하며 샘플링.
        """
        tf = target_filter or {}
        age_min = max(self._min_age, int(tf.get("age_min", self._min_age)))
        age_max = int(tf.get("age_max", _OPEN_BAND_TOP))
        gender_filter = tf.get("gender")

        cells: list[tuple[tuple[int, int, str], float]] = []
        for b in self._population["bands"]:
            lo, hi = _band_range(b["age_band"])
            lo, hi = max(lo, age_min), min(hi, age_max)
            if lo > hi:
                continue
            full = _band_range(b["age_band"])
            frac = (hi - lo + 1) / (full[1] - full[0] + 1)  # 부분 절단 시 가중치 비례 축소
            band_weight = b["share"] * frac
            for sex, ratio in (("M", b["male_ratio"]), ("F", 1 - b["male_ratio"])):
                if gender_filter and sex != gender_filter:
                    continue
                cells.append(((lo, hi, sex), band_weight * ratio))
        return cells

    def _sample_ocean(self, rng: random.Random, age: int) -> dict[str, float]:
        """OCEAN(factor score) — 논문 5유형 중 실비율로 하나 골라 그 유형의 mean·sd로 샘플링.

        유형 비율은 type_proportions(연령 무관 전체 비율). 결과는 표준화 factor score(평균≈0).
        """
        lo, hi = _OCEAN_CLIP
        dims = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
        profiles = self._ocean["type_profiles"]
        props = self._ocean["type_proportions"]["default"]
        profile = _weighted_choice(
            rng, [(profiles[n], w) for n, w in props.items() if n in profiles]
        )
        return {
            d: round(min(hi, max(lo, rng.gauss(profile[d]["mean"], profile[d]["sd"]))), 2)
            for d in dims
        }

    def _sample_media(self, rng: random.Random) -> dict[str, Any]:
        # 단계2-β stub — KISDI raw 확보 후 실분포로 교체(미디어 다이어리→exposure_context).
        return {"sns_hours": rng.randint(1, 6), "_source": "stub(KISDI raw 대기)"}

    def _sample_consumption(self, rng: random.Random, age: int) -> dict[str, bool]:
        values = dict(self._consumption["values"])
        if age <= _Z_GEN_MAX_AGE:
            values.update(self._consumption.get("generation_specific", {}).get("Z세대", {}))
        return {name: rng.random() < rate for name, rate in values.items()}
