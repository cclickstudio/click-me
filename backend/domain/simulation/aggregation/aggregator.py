# 집계 엔진 — 반응 구조화 필드를 코드로 집계 (LLM 아님). "숫자는 집계 엔진"
#
# QA 통과분만 집계. click_intent_rate 의 신뢰구간은 부트스트랩(순수 stdlib·결정적),
# variance_warning 은 구매의도 분포 집중도(REPORT §2-2 "응답 집중" 경고)로 산출.
from __future__ import annotations

import random

from domain.simulation.contracts.schemas import PersonaReaction, SimulationAggregate

ENGINE_VERSION = "agg-1"

# 부트스트랩 설정 — 결정적 재현을 위해 시드 고정.
_BOOTSTRAP_ITERS = 2000
_BOOTSTRAP_SEED = 0
_ALPHA = 0.05  # 95% CI

# 구매의도(1~5) 표준편차가 이 값 미만이면 응답 집중 경고(동질화 의심).
_VARIANCE_MIN_STD = 0.5


def _stdev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / (n - 1)) ** 0.5


def _bootstrap_ci(flags: list[int]) -> tuple[float, float]:
    """비율(0/1 플래그)의 백분위 부트스트랩 95% CI. 결정적(시드 고정)."""
    n = len(flags)
    if n == 0:
        return 0.0, 0.0
    rng = random.Random(_BOOTSTRAP_SEED)
    means = sorted(
        sum(flags[rng.randrange(n)] for _ in range(n)) / n for _ in range(_BOOTSTRAP_ITERS)
    )
    lo = means[int((_ALPHA / 2) * _BOOTSTRAP_ITERS)]
    hi = means[int((1 - _ALPHA / 2) * _BOOTSTRAP_ITERS)]
    return lo, hi


class BasicAggregator:
    """집계 엔진 — QA 통과분만 집계."""

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
                variance_warning=True,
                payload={"note": "QA 통과 표본 없음", "qa_passed_count": 0},
                engine_version=ENGINE_VERSION,
            )

        action_flags = [int(r.aisas.action) for r in passed]
        purchases = [float(r.purchase_intent) for r in passed]
        click_rate = sum(action_flags) / n
        ci_low, ci_high = _bootstrap_ci(action_flags)
        purchase_std = _stdev(purchases)

        return SimulationAggregate(
            click_intent_rate=round(click_rate, 4),
            ci_low=round(ci_low, 4),
            ci_high=round(ci_high, 4),
            purchase_intent=round(sum(purchases) / n, 2),
            trust_avg=round(sum(r.trust for r in passed) / n, 2),
            rejection_rate=round(sum(1 for r in passed if r.rejected) / n, 4),
            variance_warning=purchase_std < _VARIANCE_MIN_STD,
            payload={
                "qa_passed_count": n,
                "ci_method": "bootstrap",
                "ci_iters": _BOOTSTRAP_ITERS,
                "purchase_std": round(purchase_std, 3),
            },
            engine_version=ENGINE_VERSION,
        )
