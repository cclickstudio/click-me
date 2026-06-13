# 집계 엔진 — 반응 구조화 필드를 코드로 집계 (LLM 아님). "숫자는 집계 엔진"
#
# 구조만 확정한 상태. 신뢰구간(부트스트랩)·variance_warning 정식 산출은 추후 구현.
from __future__ import annotations

from domain.simulation.contracts.schemas import PersonaReaction, SimulationAggregate

ENGINE_VERSION = "agg-0"


class BasicAggregator:
    """집계 엔진 — QA 통과분만 집계.

    현재: 평균/비율만 산출. ci_low/high·variance_warning 은 placeholder(TODO).
    """

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
                payload={"note": "QA 통과 표본 없음"},
                engine_version=ENGINE_VERSION,
            )

        click_rate = sum(1 for r in passed if r.aisas.action) / n
        purchase = sum(r.purchase_intent for r in passed) / n
        trust = sum(r.trust for r in passed) / n
        rejection = sum(1 for r in passed if r.rejected) / n

        # TODO(추후): 부트스트랩 신뢰구간 + 분산 기반 variance_warning 산출
        ci_margin = 0.0
        return SimulationAggregate(
            click_intent_rate=round(click_rate, 4),
            ci_low=round(max(0.0, click_rate - ci_margin), 4),
            ci_high=round(min(1.0, click_rate + ci_margin), 4),
            purchase_intent=round(purchase, 2),
            trust_avg=round(trust, 2),
            rejection_rate=round(rejection, 4),
            variance_warning=False,
            payload={"qa_passed_count": n, "ci_method": "TODO"},
            engine_version=ENGINE_VERSION,
        )
