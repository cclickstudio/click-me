# 집계 엔진 — 반응 구조화 필드를 코드로 집계 (LLM 아님). "숫자는 집계 엔진"
#
# QA 통과분만 집계. click_intent_rate 의 신뢰구간은 부트스트랩(순수 stdlib·결정적),
# variance_warning 은 구매의도 분포 집중도(REPORT §2-2 "응답 집중" 경고)로 산출.
from __future__ import annotations

import random

from domain.simulation.contracts.schemas import PersonaReaction, SimulationAggregate

ENGINE_VERSION = "agg-2"  # agg-2: 가중 집계(§3.7) — 가중 평균·가중 부트스트랩·유효표본

# 부트스트랩 설정 — 결정적 재현을 위해 시드 고정.
_BOOTSTRAP_ITERS = 2000
_BOOTSTRAP_SEED = 0
_ALPHA = 0.05  # 95% CI

# 구매의도(1~5) (가중)표준편차가 이 값 미만이면 응답 집중 경고(동질화 의심).
_VARIANCE_MIN_STD = 0.5


def _wmean(values: list[float], weights: list[float]) -> float:
    sw = sum(weights)
    return sum(v * w for v, w in zip(values, weights, strict=True)) / sw if sw else 0.0


def _wstd(values: list[float], weights: list[float]) -> float:
    """가중 표준편차 — 응답 집중(동질화) 판정용."""
    sw = sum(weights)
    if sw <= 0:
        return 0.0
    m = _wmean(values, weights)
    var = sum(w * (v - m) ** 2 for v, w in zip(values, weights, strict=True)) / sw
    return var**0.5


def _effective_n(weights: list[float]) -> float:
    """Kish 유효표본수 = (Σw)² / Σ(w²). 균일 가중이면 = n, 편차 클수록 작아짐."""
    s1 = sum(weights)
    s2 = sum(w * w for w in weights)
    return (s1 * s1 / s2) if s2 else 0.0


def _weighted_bootstrap_ci(flags: list[float], weights: list[float]) -> tuple[float, float]:
    """가중 비율의 백분위 부트스트랩 95% CI. 표본 단위를 균등 재추출하되 가중 추정량을 매번 재계산.

    결정적(시드 고정). 가중 편차가 크면 CI가 넓어져 표본 정밀도를 정직하게 반영한다.
    """
    n = len(flags)
    if n == 0:
        return 0.0, 0.0
    rng = random.Random(_BOOTSTRAP_SEED)
    means = []
    for _ in range(_BOOTSTRAP_ITERS):
        idx = [rng.randrange(n) for _ in range(n)]
        sw = sum(weights[i] for i in idx)
        means.append(sum(flags[i] * weights[i] for i in idx) / sw if sw else 0.0)
    means.sort()
    lo = means[int((_ALPHA / 2) * _BOOTSTRAP_ITERS)]
    hi = means[int((1 - _ALPHA / 2) * _BOOTSTRAP_ITERS)]
    return lo, hi


def _ssr_population_probs(reactions: list[PersonaReaction], dim: str) -> list[float] | None:
    """SSR 분포(1~5 raw_probs)의 가중 평균 → population 분포. dist 있는 반응만, 없으면 None.

    SIMULATION_SCORING=ssr 경로에서만 값이 생긴다(§KPI 분포 표기 근거) — 미사용 시 payload 무변화.
    """
    pairs = [
        (dist.raw_probs, float(r.weight))
        for r in reactions
        if (dist := getattr(r, dim)) is not None and len(dist.raw_probs) == 5
    ]
    if not pairs:
        return None
    sw = sum(w for _, w in pairs)
    if sw <= 0:
        return None
    return [round(sum(probs[i] * w for probs, w in pairs) / sw, 4) for i in range(5)]


class BasicAggregator:
    """집계 엔진 — QA 통과분만, 페르소나 가중치로 가중 집계(§3.7)."""

    def aggregate(self, reactions: list[PersonaReaction]) -> SimulationAggregate:
        passed = [r for r in reactions if r.qa_passed]
        n = len(passed)
        if n == 0:
            return SimulationAggregate(
                click_intent_rate=0.0,
                ci_low=0.0,
                ci_high=0.0,
                purchase_intent=0.0,
                trust_avg=0.0,
                rejection_rate=0.0,
                brand_recognition_rate=0.0,
                variance_warning=True,
                effective_n=0.0,
                payload={"note": "QA 통과 표본 없음", "qa_passed_count": 0},
                engine_version=ENGINE_VERSION,
            )

        weights = [float(r.weight) for r in passed]
        action_flags = [float(r.aisas.action) for r in passed]
        purchases = [float(r.purchase_intent) for r in passed]
        ci_low, ci_high = _weighted_bootstrap_ci(action_flags, weights)
        purchase_std = _wstd(purchases, weights)
        eff_n = _effective_n(weights)

        # SSR population 분포(opt-in) — dist 있는 반응만 가중 합성. 없으면 payload 무변화.
        ssr_payload: dict = {}
        pi_probs = _ssr_population_probs(passed, "purchase_intent_dist")
        trust_probs = _ssr_population_probs(passed, "trust_dist")
        if pi_probs is not None:
            ssr_payload["ssr_purchase_intent_probs"] = pi_probs
        if trust_probs is not None:
            ssr_payload["ssr_trust_probs"] = trust_probs
        if ssr_payload:
            ssr_payload["ssr_dist_n"] = sum(
                1 for r in passed if r.purchase_intent_dist or r.trust_dist
            )

        # 4자리 반올림 — DB Numeric(5,4)와 정합. 집행 게이트 알림↔from_simulation 판정 일치 보장.
        # 자릿수 변경 시 domain/simulation/models.py 컬럼 정의도 함께 조정.
        return SimulationAggregate(
            click_intent_rate=round(_wmean(action_flags, weights), 4),
            ci_low=round(ci_low, 4),
            ci_high=round(ci_high, 4),
            purchase_intent=round(_wmean(purchases, weights), 2),
            trust_avg=round(_wmean([float(r.trust) for r in passed], weights), 2),
            rejection_rate=round(_wmean([float(r.rejected) for r in passed], weights), 4),
            brand_recognition_rate=round(
                _wmean([float(r.brand_recognized) for r in passed], weights), 4
            ),
            variance_warning=purchase_std < _VARIANCE_MIN_STD,
            effective_n=round(eff_n, 1),
            payload={
                "qa_passed_count": n,
                "ci_method": "weighted_bootstrap",
                "ci_iters": _BOOTSTRAP_ITERS,
                "purchase_std": round(purchase_std, 3),
                "weight_sum": round(sum(weights), 1),
                **ssr_payload,
            },
            engine_version=ENGINE_VERSION,
        )
