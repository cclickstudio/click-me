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
from domain.simulation.tools.sampling.raking import rake_weights

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


def _generation_of_age(age: int) -> str:
    """실 나이 → 세대 라벨(social_values_deep generation_specific 키)."""
    if age <= _Z_GEN_MAX_AGE:
        return "Z세대"
    if age <= 44:
        return "밀레니얼"
    if age <= 59:
        return "X세대"
    return "베이비부머"


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


# OCEAN 5차원(type_profiles·band_factor_means 공통 키 순서).
_OCEAN_DIMS = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")


def _band_factor_offsets(ocean: dict[str, Any]) -> dict[str, dict[str, float]]:
    """밴드별 factor 잔차 offset = 실측 밴드평균 − (밴드 유형비율 × 유형 프로파일 평균).

    유형비율 조건화만으론 성숙원리(성실성·친화성↑·신경증↓)의 일부만 재현된다(유형 내 노화 미반영).
    실측 평균이 있으면 잔차로 밴드 marginal을 실측에 정합. 연령×성별('밴드|성별') 우선, 연령만 폴백.
    """
    profiles = ocean.get("type_profiles", {})
    tp = ocean.get("type_proportions", {})
    by_band = tp.get("by_age_band", {})
    by_gender = tp.get("by_age_gender_band", {})
    default = tp.get("default", {})

    def residual(observed: dict[str, float], props: dict[str, float]) -> dict[str, float]:
        wsum = sum(props.values()) or 1.0
        out: dict[str, float] = {}
        for d in _OCEAN_DIMS:
            implied = sum(props[t] * profiles[t][d]["mean"] for t in props if t in profiles) / wsum
            out[d] = round(observed[d] - implied, 4)
        return out

    offsets: dict[str, dict[str, float]] = {}
    for key, observed in ocean.get("band_factor_means_by_gender", {}).items():
        if key.startswith("_"):  # _source 등 메타 키 건너뜀.
            continue
        offsets[key] = residual(
            observed, by_gender.get(key) or by_band.get(key.split("|")[0]) or default
        )
    for band, observed in ocean.get("band_factor_means", {}).items():
        if band.startswith("_"):
            continue
        offsets[band] = residual(observed, by_band.get(band) or default)
    return offsets


# OCEAN→행동 경량 조건화(문헌 prior, 진짜 성격×행동 joint 아님) — 표준화 factor score당 보정.
_OCEAN_VALUE_NUDGE = {
    # 소비가치: (OCEAN 차원, 계수). 성실성↑→성능·품질 중시, 개방성↑→취향·덕질(신규·니치 선호).
    "성능": ("conscientiousness", 0.05),
    "품질": ("conscientiousness", 0.05),
    "취향·덕질": ("openness", 0.06),
}


def _nudge_rate(rate: float, ocean: dict[str, float], dim: str, k: float) -> float:
    """소비가치 보유확률을 OCEAN으로 소폭 보정 — 안전 클립[0.02, 0.98]."""
    return min(0.98, max(0.02, rate + k * ocean.get(dim, 0.0)))


def _media_minutes_factor(ocean: dict[str, float]) -> float:
    """OCEAN→미디어 이용시간 경량 보정 — 개방성·외향성↑이면 매체 이용 다소↑(클립 0.85~1.15)."""
    raw = ocean.get("openness", 0.0) + ocean.get("extraversion", 0.0)
    return min(1.15, max(0.85, 1.0 + 0.04 * raw))


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
    """분포에서 페르소나 속성 묶음을 샘플링. CachedPanelProvider 와 동일한 get_or_build 시그니처."""

    def __init__(
        self,
        *,
        population: dict | None = None,
        ocean: dict | None = None,
        consumption: dict | None = None,
        media: dict | None = None,
        socioeconomic: dict | None = None,
        meta_reach: dict | None = None,
        social_values_deep: dict | None = None,
        social_economic: dict | None = None,
        min_age: int = _MIN_AGE,
        reachability_sampling: bool = False,
        platform: str | None = None,
        rake_to_census: bool = False,
    ) -> None:
        self._population = population or loader.load_population_age_sex()
        self._ocean = ocean or loader.load_ocean_age_bands()
        self._consumption = consumption or loader.load_consumption_values()
        self._media = media or loader.load_media_behavior()
        self._socioeconomic = socioeconomic or loader.load_socioeconomic()
        # 단계3 한국 특화 심리(체면·동조·눈치) — 값 미확보면 generation_specific 비어 샘플 시 {}.
        self._social_values_deep = social_values_deep or loader.load_social_values_deep()
        # 사회경제·심리 prior(세대별, MDIS 사회조사) — 값 비면 샘플 시 {}(graceful).
        self._social_economic = social_economic or loader.load_social_economic()
        # Meta 침투율 곡선(Tier 2) — 연령별 인스타/페북 사용률. reach 가중의 출처.
        self._meta_reach = meta_reach or loader.load_meta_reach()
        self._min_age = min_age
        # Meta 전용 경로 — 켜면 연령×성별 표본을 인구×메타침투율 비율로 뽑는다(§Tier2).
        # 가중이 아니라 추출분포를 바꿈(self-weighting 유지) → 메타 도달층에 표본 집중, CI 효율↑.
        # 기본 OFF: 전인구 비례(§3.7)·기존 테스트 보존. wiring 에서만 ON.
        self._reachability_sampling = reachability_sampling
        # Meta 플랫폼(instagram/facebook) — 지정 + 실데이터 있으면 그 분포, 없으면 통합 reach 폴백.
        self._platform = platform
        # 외부 marginal raking — 켜면 가중치를 census 나이·성별에 IPF 정합(기본 OFF, 회귀 보존).
        self._rake_to_census = rake_to_census
        # 밴드별 factor 잔차 offset(성숙원리 정량 반영) — 1회 산출 후 _sample_ocean에서 가산.
        self._ocean_band_offset = _band_factor_offsets(self._ocean)

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
            personas = self._sample_stratified(spec, cells, regions, rng)
        else:
            personas = self._sample_proportional(spec, cells, regions, rng)
        if self._rake_to_census:
            personas = self._apply_census_raking(personas)
        return personas

    def _apply_census_raking(self, personas: list[Persona]) -> list[Persona]:
        """패널 가중치를 census(인구) 나이밴드·성별 marginal에 IPF 정합 — 편향 보정(§3.7).

        도달성 과표집 등으로 틀어진 가중을 외부 marginal에 맞춰 되돌린다. 인구 분포 없으면 무변화.
        """
        bands = self._population.get("bands") or []
        if not bands:
            return personas
        age_target = {b["age_band"]: b["share"] for b in bands}
        male = sum(b["share"] * b.get("male_ratio", 0.5) for b in bands)
        gender_target = {"M": male, "F": 1.0 - male}
        weights = rake_weights(
            personas,
            [
                (lambda p: media_band_of_age(p.age), age_target),
                (lambda p: p.gender, gender_target),
            ],
            base_weights=[p.weight for p in personas],
        )
        return [p.model_copy(update={"weight": w}) for p, w in zip(personas, weights, strict=True)]

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
        ocean = self._sample_ocean(rng, age, sex)
        # 도달성은 추출분포(_population_cells)에 이미 반영 — 여기선 self-weighting(weight 그대로).
        return Persona(
            persona_id=f"P-{idx:05d}",
            age=age,
            gender=sex,
            region=_weighted_choice(rng, regions),
            ocean=ocean,
            media_behavior=self._sample_media(rng, age, sex, ocean),
            consumption_values=self._sample_consumption(rng, age, ocean),
            socioeconomic=self._sample_socioeconomic(rng, age, sex),
            social_values_deep=self._sample_social_values_deep(age, ocean),
            social_economic=self._sample_social_economic(age),
            weight=weight,
            profile_narrative="",  # 4-a(LLM)에서 채움 — P3
        )

    def _sample_social_values_deep(self, age: int, ocean: dict[str, float]) -> dict[str, float]:
        """단계3 한국 특화 심리(체면·동조·눈치) — generation_specific 비면 {}(비활성·폴백).

        데이터 확보 시 세대 base를 OCEAN으로 조건부 보정. 현재 값 비움이라 빈 dict 반환.
        """
        gen_map = self._social_values_deep.get("generation_specific") or {}
        if not gen_map:
            return {}
        base = gen_map.get(_generation_of_age(age), {})
        return {k: round(max(0.0, min(1.0, float(v))), 3) for k, v in base.items()}

    def _sample_social_economic(self, age: int) -> dict[str, float]:
        """세대별 사회경제·심리 prior — 값 비면 {}(graceful)."""
        gen_map = self._social_economic.get("generation_specific") or {}
        if not gen_map:
            return {}
        base = gen_map.get(_generation_of_age(age), {})
        return {k: round(max(0.0, min(1.0, float(v))), 3) for k, v in base.items()}

    def _population_cells(
        self, target_filter: dict | None
    ) -> list[tuple[tuple[int, int, str], float]]:
        """연령밴드×성별 셀 목록. target_filter(age_min/age_max/gender)로 조건부 필터·재가중.

        Layer1 스킵 금지 — 필터 안에서도 실분포(밴드 share·성비)를 유지하며 샘플링.
        """
        tf = target_filter or {}
        user_min = tf.get("age_min")  # 사용자 지정만 분리 — 기본 min_age 절단과 구분(§Tier2-A)
        user_max = tf.get("age_max")
        age_min = max(self._min_age, int(user_min) if user_min is not None else self._min_age)
        age_max = int(user_max) if user_max is not None else _OPEN_BAND_TOP
        gender_filter = tf.get("gender")

        cells: list[tuple[tuple[int, int, str], float]] = []
        for b in self._population["bands"]:
            full_lo, full_hi = _band_range(b["age_band"])
            lo, hi = max(full_lo, age_min), min(full_hi, age_max)
            if lo > hi:
                continue
            span = full_hi - full_lo + 1
            if self._reachability_sampling:
                # Meta 도달 분포를 연령 marginal로 직접 사용(§Tier2-A). 메타 추산치는 census
                # 인구를 초과(복수계정 등)해 침투율이 아닌 '도달 marginal' → 인구비중 곱 금지.
                # frac은 '사용자 지정' 연령 절단만 반영 — 기본 min_age(14) 절단으로는 축소하지
                # 않는다. 도달 marginal은 밴드 내 실제 연령 분포를 이미 담아 균등 가정 축소가 왜곡.
                u_lo = max(full_lo, int(user_min)) if user_min is not None else full_lo
                u_hi = min(full_hi, int(user_max)) if user_max is not None else full_hi
                frac = (u_hi - u_lo + 1) / span if u_hi >= u_lo else 0.0
                band_weight = self._reach_marginal(b["age_band"]) * frac
            else:
                frac = (hi - lo + 1) / span  # 부분 절단 시 가중치 비례 축소(인구 균등 가정)
                band_weight = b["share"] * frac
            for sex, ratio in (("M", b["male_ratio"]), ("F", 1 - b["male_ratio"])):
                if gender_filter and sex != gender_filter:
                    continue
                cells.append(((lo, hi, sex), band_weight * ratio))
        return cells

    def _reach_age_bands(self) -> dict[str, float]:
        """도달 연령 marginal — 플랫폼(IG/FB) 지정 + 실데이터 있으면 그것, 없으면 통합 age_bands."""
        if self._platform:
            spec = self._meta_reach.get("platform_specifics", {}).get(self._platform, {})
            bands = spec.get("age_bands")
            if bands:
                return bands
        return self._meta_reach.get("age_bands", {})

    def _reach_marginal(self, band_key: str) -> float:
        """Meta 도달 분포에서 밴드의 도달 점유율(연령 marginal). 없으면 0(§Tier2-A)."""
        return self._reach_age_bands().get(band_key, 0.0)

    def _cell_reach(self, age: int, gender: str) -> float:
        """연령(+플랫폼 지정 시 성별)의 Meta 도달 점유율(0~1). 데이터 없으면 0. 페르소나 기록용.

        플랫폼(IG/FB) 지정 + by_age_gender 실데이터 있으면 연령×성별 값, 없으면 연령 marginal 폴백.
        과거 KISDI 소셜피드 비중(영상 위주)과 어긋나 Meta 광고관리자 실측 도달로 교체(§Tier2-A).
        """
        band = media_band_of_age(age)
        if self._platform:
            spec = self._meta_reach.get("platform_specifics", {}).get(self._platform, {})
            v = (spec.get("by_age_gender") or {}).get(f"{band}|{gender}")
            if v is not None:
                return v
        return self._reach_age_bands().get(band, 0.0)

    def _sample_ocean(self, rng: random.Random, age: int, gender: str) -> dict[str, float]:
        """OCEAN(factor score) — 논문 5유형 중 실비율로 하나 골라 그 유형의 mean·sd로 샘플링.

        유형 비율은 연령×성별 실측(by_age_gender_band) 우선 → 연령만(by_age_band) → default 폴백.
        밴드 factor 잔차 offset도 성별 우선 적용해 남녀 성격 차이(여>남 신경증·친화성)를 반영.
        """
        lo, hi = _OCEAN_CLIP
        band = ocean_band_of_age(age)
        key = f"{band}|{gender}"
        tp = self._ocean["type_proportions"]
        props = (
            tp.get("by_age_gender_band", {}).get(key)
            or tp.get("by_age_band", {}).get(band)
            or tp["default"]
        )
        profiles = self._ocean["type_profiles"]
        profile = _weighted_choice(
            rng, [(profiles[n], w) for n, w in props.items() if n in profiles]
        )
        offset = self._ocean_band_offset.get(key) or self._ocean_band_offset.get(band, {})
        out: dict[str, float] = {}
        for d in _OCEAN_DIMS:
            v = rng.gauss(profile[d]["mean"], profile[d]["sd"]) + offset.get(d, 0.0)
            out[d] = round(min(hi, max(lo, v)), 2)
        return out

    def _media_cell(self, age: int, gender: str) -> dict | None:
        """연령×성별 미디어 셀 조회. v2(cells) 없으면 None(평면 fallback)."""
        cells = self._media.get("cells")
        if not cells:
            return None
        return cells.get(f"{media_band_of_age(age)}|{gender}")

    def _sample_media(
        self, rng: random.Random, age: int, gender: str, ocean: dict[str, float]
    ) -> dict[str, Any]:
        # 단계2-β — KISDI 다이어리 연령×성별 셀: 주매체(사용시간 가중)·일일분·노출맥락 후보.
        f = _media_minutes_factor(ocean)  # OCEAN 경량 조건화(개방성·외향성↑→이용시간↑)
        cell = self._media_cell(age, gender)
        if cell is None:  # 평면 포맷(구버전 JSON) 폴백
            dm = self._media["device_minutes"]
            primary = _weighted_choice(rng, list(dm.items()))
            avg = dm[primary]
            return {
                "primary_medium": primary,
                "daily_media_minutes": max(5, round(rng.gauss(avg * f, avg * 0.35))),
                "_source": "KISDI 표4-71(평면)",
            }
        dm = cell["device_minutes"]
        primary = _weighted_choice(rng, list(dm.items())) if dm else "스마트폰/휴대폰"
        mm = cell["daily_media_minutes"]
        minutes = max(5, round(rng.gauss(mm["mean"] * f, mm["sd"])))
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

    def _sample_consumption(
        self, rng: random.Random, age: int, ocean: dict[str, float]
    ) -> dict[str, bool]:
        values = dict(self._consumption["values"])
        if age <= _Z_GEN_MAX_AGE:
            values.update(self._consumption.get("generation_specific", {}).get("Z세대", {}))
        out: dict[str, bool] = {}
        for name, rate in values.items():
            spec = _OCEAN_VALUE_NUDGE.get(name)  # OCEAN 경량 조건화(있는 가치만)
            adj = _nudge_rate(rate, ocean, *spec) if spec else rate
            out[name] = rng.random() < adj
        return out
