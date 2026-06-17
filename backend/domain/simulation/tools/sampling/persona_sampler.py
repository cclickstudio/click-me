# 페르소나 속성 샘플러 — 단계1~3을 통계 분포에서 샘플링 (LLM✗, 동질화 방어 1차 방어선)
#
# 단계1 인구(연령×성별, target_filter 조건부) → 2-α OCEAN(연령조건) → 2-β 행동(stub) → 3 소비가치.
# 서사(4-a)는 여기서 만들지 않는다(profile_narrative=""). 결정적(spec.seed) — 고정 패널 재현용.
# 분포가 placeholder/실데이터 무엇이든 동일 코드로 동작. data_status()로 grounding 상태 확인.
from __future__ import annotations

import random
from typing import Any

from domain.simulation.contracts.schemas import PanelSpec, Persona
from domain.simulation.data.simulation import loader
from domain.simulation.tools.reachability import cell_social_reach, is_social_context

# 지역 분포 폴백 — 행안부 원본 CSV에 시도(region_weights)가 있으면 그걸 우선 사용. 합=1.0.
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
_STRAT_FLOOR = 10  # 층화 배분 시 셀당 최소 표본(분산 큰/표본 얇은 층 보강, §3.7 b).


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


def media_band_of_age(age: int) -> str:
    """실제 나이를 미디어행동(KISDI) 연령밴드로 매핑 — OCEAN과 구간이 다름(60-69/70+ 분리)."""
    if age >= 70:
        return "70+"
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


def _largest_remainder(weights: list[float], total: int) -> list[int]:
    """비례 정수 배분(최대잔여법) — 합이 정확히 total. 라운딩 편향 없음."""
    s = sum(weights) or 1.0
    raw = [total * w / s for w in weights]
    base = [int(x) for x in raw]
    leftover = total - sum(base)
    order = sorted(range(len(weights)), key=lambda i: raw[i] - base[i], reverse=True)
    for j in range(leftover):
        base[order[j]] += 1
    return base


def _stratified_allocation(
    pop_weights: list[float], size: int, floor: int
) -> list[tuple[int, float]]:
    """층화 배분 — 셀당 floor 보장 후 나머지를 인구비례 배분. 반환: 셀별 (표본수, 가중치).

    가중치 = 인구비중 / 표본비중 → 과대표집 셀 w<1, 과소표집 셀 w>1 (가중 집계 시 모집단 불편).
    """
    k = len(pop_weights)
    if size < floor * k:  # 표본이 작으면 floor 축소(최소 1)
        floor = max(1, size // k)
    rem = size - floor * k
    counts = (
        [floor + n for n in _largest_remainder(pop_weights, rem)]
        if rem > 0
        else _largest_remainder(pop_weights, size)
    )
    total_w = sum(pop_weights) or 1.0
    n = sum(counts) or 1
    out: list[tuple[int, float]] = []
    for w, c in zip(pop_weights, counts, strict=True):
        pop_share = w / total_w
        samp_share = c / n if c else 1.0
        out.append((c, pop_share / samp_share if samp_share else 0.0))
    return out


class PersonaSampler:
    """분포에서 페르소나 속성 묶음을 샘플링. MockPanelProvider 와 동일한 get_or_build 시그니처."""

    def __init__(
        self,
        *,
        population: dict | None = None,
        ocean: dict | None = None,
        consumption: dict | None = None,
        media: dict | None = None,
        socioeconomic: dict | None = None,
        meta_reach: dict | None = None,
        min_age: int = _MIN_AGE,
        reachability_sampling: bool = False,
    ) -> None:
        self._population = population or loader.load_population_age_sex()
        self._ocean = ocean or loader.load_ocean_age_bands()
        self._consumption = consumption or loader.load_consumption_values()
        self._media = media or loader.load_media_behavior()
        self._socioeconomic = socioeconomic or loader.load_socioeconomic()
        # Meta 침투율 곡선(Tier 2) — 연령별 인스타/페북 사용률. reach 가중의 출처.
        self._meta_reach = meta_reach or loader.load_meta_reach()
        self._min_age = min_age
        # Meta 전용 경로 — 켜면 연령×성별 표본을 인구×메타침투율 비율로 뽑는다(§Tier2).
        # 가중이 아니라 추출분포를 바꿈(self-weighting 유지) → 메타 도달층에 표본 집중, CI 효율↑.
        # 기본 OFF: 전인구 비례(§3.7)·기존 테스트 보존. wiring 에서만 ON.
        self._reachability_sampling = reachability_sampling

    async def get_or_build(self, spec: PanelSpec) -> tuple[str, list[Persona]]:
        return spec.version, self.sample(spec)

    def sample(self, spec: PanelSpec) -> list[Persona]:
        rng = random.Random(spec.seed)
        cells = self._population_cells(spec.target_filter)
        if not cells:
            raise ValueError("target_filter 가 모든 인구 셀을 제외했습니다.")
        # 시도 실분포(행안부 원본)가 있으면 우선, 없으면 근사 폴백.
        regions = list((self._population.get("region_weights") or _REGION_WEIGHTS).items())

        if spec.allocation == "stratified":
            return self._sample_stratified(spec, cells, regions, rng)
        return self._sample_proportional(spec, cells, regions, rng)

    def _sample_proportional(
        self, spec: PanelSpec, cells: list, regions: list, rng: random.Random
    ) -> list[Persona]:
        """비례 정수 배분(쿼터, self-weighting) — 셀(연령×성별)별 인원을 인구 비례로 확정.

        최대잔여법. 독립 추첨이 아니라 쿼터라 작은 표본도 연령·성별 구성 안정(인구 20%→표본 ~20%).
        셀 안의 나이·지역·OCEAN 등은 여전히 랜덤(다차원이라 불가피). 가중치 1.0(§3.7).
        """
        counts = _largest_remainder([w for _, w in cells], spec.size)
        personas: list[Persona] = []
        i = 0
        for (cell, _w), n_c in zip(cells, counts, strict=True):
            band_lo, band_hi, sex = cell
            for _ in range(n_c):
                personas.append(self._build_persona(i, band_lo, band_hi, sex, regions, rng, 1.0))
                i += 1
        return personas

    def _sample_stratified(
        self, spec: PanelSpec, cells: list, regions: list, rng: random.Random
    ) -> list[Persona]:
        """층화 과대표집(§3.7 b) — 표본 얇은 층을 floor로 보강하고, 과대표집을 가중치로 보정.

        weight = 인구비중/표본비중 → 더 뽑힌 셀 w<1, 덜 뽑힌 셀 w>1. 가중 집계 시 모집단 불편추정.
        """
        plan = _stratified_allocation([w for _, w in cells], spec.size, _STRAT_FLOOR)
        personas: list[Persona] = []
        i = 0
        for (cell, _w), (n_c, weight) in zip(cells, plan, strict=True):
            band_lo, band_hi, sex = cell
            for _ in range(n_c):
                personas.append(self._build_persona(i, band_lo, band_hi, sex, regions, rng, weight))
                i += 1
        return personas

    def _build_persona(
        self,
        idx: int,
        band_lo: int,
        band_hi: int,
        sex: str,
        regions: list,
        rng: random.Random,
        weight: float,
    ) -> Persona:
        age = rng.randint(band_lo, band_hi)
        # 도달성은 추출분포(_population_cells)에 이미 반영 — 여기선 self-weighting(weight 그대로).
        return Persona(
            persona_id=f"P-{idx:05d}",
            age=age,
            gender=sex,
            region=_weighted_choice(rng, regions),
            ocean=self._sample_ocean(rng, age),
            media_behavior=self._sample_media(rng, age, sex),
            consumption_values=self._sample_consumption(rng, age),
            socioeconomic=self._sample_socioeconomic(rng, age, sex),
            weight=weight,
            profile_narrative="",  # 4-a(LLM)에서 채움 — P3
        )

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
            if self._reachability_sampling:
                # Meta 도달 분포를 연령 marginal로 직접 사용(§Tier2-A). 메타 추산치는 census
                # 인구를 초과(복수계정 등)해 침투율이 아닌 '도달 marginal' → 인구비중 곱 금지.
                band_weight = self._reach_marginal(b["age_band"]) * frac
            else:
                band_weight = b["share"] * frac
            for sex, ratio in (("M", b["male_ratio"]), ("F", 1 - b["male_ratio"])):
                if gender_filter and sex != gender_filter:
                    continue
                cells.append(((lo, hi, sex), band_weight * ratio))
        return cells

    def _reach_marginal(self, band_key: str) -> float:
        """Meta 도달 분포에서 밴드의 도달 점유율(연령 marginal). 없으면 0(§Tier2-A)."""
        return self._meta_reach.get("age_bands", {}).get(band_key, 0.0)

    def _cell_reach(self, age: int, gender: str) -> float:
        """연령의 Meta 도달 점유율(0~1, §Tier2-A). 데이터 없으면 0. 페르소나 기록용 참고치.

        과거엔 KISDI 소셜피드 비중(cell_social_reach)을 썼으나 사실상 유튜브 영상 시청만 잡혀
        메타와 어긋남 → Meta 광고 관리자 실측 도달 분포로 교체. 추출 가중은 _reach_marginal이
        담당하고 여기선 동일 값을 페르소나 속성으로 노출. gender 는 시그니처만 유지(현재 미사용).
        """
        band = media_band_of_age(age)
        return self._meta_reach.get("age_bands", {}).get(band, 0.0)

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

    def _media_cell(self, age: int, gender: str) -> dict | None:
        """연령×성별 미디어 셀 조회. v2(cells) 없으면 None(평면 fallback)."""
        cells = self._media.get("cells")
        if not cells:
            return None
        return cells.get(f"{media_band_of_age(age)}|{gender}")

    def _sample_media(self, rng: random.Random, age: int, gender: str) -> dict[str, Any]:
        # 단계2-β — KISDI 다이어리 연령×성별 셀: 주매체(사용시간 가중)·일일분·노출맥락 후보.
        cell = self._media_cell(age, gender)
        if cell is None:  # 평면 포맷(구버전 JSON) 폴백
            dm = self._media["device_minutes"]
            primary = _weighted_choice(rng, list(dm.items()))
            avg = dm[primary]
            return {
                "primary_medium": primary,
                "daily_media_minutes": max(5, round(rng.gauss(avg, avg * 0.35))),
                "_source": "KISDI 표4-71(평면)",
            }
        dm = cell["device_minutes"]
        primary = _weighted_choice(rng, list(dm.items())) if dm else "스마트폰/휴대폰"
        mm = cell["daily_media_minutes"]
        minutes = max(5, round(rng.gauss(mm["mean"], mm["sd"])))
        # 노출맥락 후보 — Meta 전용이므로 소셜피드(SNS·동영상 @ 스마트폰/PC) 맥락만 추린 뒤 상위 5.
        # 전체 상위5로 뽑으면 고령층은 TV가 점령해 소셜이 잘림 → 메타 광고 TV 노출 모순(§Tier1).
        candidates = [
            {
                "timeband": e["timeband"],
                "medium": e["medium"],
                "activity": e["activity"],
                "place": e["place"],
            }
            for e in cell.get("exposure", [])
            if is_social_context(e.get("activity"), e.get("medium"))
        ][:5]
        out: dict[str, Any] = {
            "primary_medium": primary,
            "daily_media_minutes": minutes,
            "exposure_candidates": candidates,
            "_source": "KISDI 한국미디어패널 2024(d25)",
        }
        out["meta_reach"] = round(
            self._cell_reach(age, gender), 4
        )  # Meta 도달 점유율 — 추출 marginal(§Tier2-A)
        reach = cell_social_reach(cell)  # KISDI 소셜피드(영상) 비중 — 노출맥락 투명성용 참고치
        if reach is not None:
            out["social_feed_reach"] = round(reach, 4)
        return out

    def _sample_socioeconomic(self, rng: random.Random, age: int, gender: str) -> dict[str, Any]:
        # 단계1 확장 — KISDI 연령×성별 셀에서 소득(8구간)·학력(6단계) 조건부 샘플링.
        cell = (self._socioeconomic.get("cells") or {}).get(f"{media_band_of_age(age)}|{gender}")
        if not cell:
            return {}
        inc_items = [(d, d["share"]) for d in cell.get("income", [])]
        edu_items = [(d, d["share"]) for d in cell.get("education", [])]
        income = _weighted_choice(rng, inc_items) if inc_items else None
        edu = _weighted_choice(rng, edu_items) if edu_items else None
        out: dict[str, Any] = {"_source": "KISDI 한국미디어패널 2024(d25)"}
        if income:
            out["income_bracket"] = income["label"]
            out["income_code"] = int(income["code"])
        if edu:
            out["education"] = edu["label"]
        return out

    def _sample_consumption(self, rng: random.Random, age: int) -> dict[str, bool]:
        values = dict(self._consumption["values"])
        if age <= _Z_GEN_MAX_AGE:
            values.update(self._consumption.get("generation_specific", {}).get("Z세대", {}))
        return {name: rng.random() < rate for name, rate in values.items()}
