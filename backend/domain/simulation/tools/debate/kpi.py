# 조각 9 — KPI 확정 + 토론 주제 생성(결정론, LLM✗)
#
# KPI는 기존 집계 엔진(BasicAggregator) 재사용 — 8(구조)이 푼 "무엇이 문제"를 9가 "숫자로" 확정.
# 토론 주제는 8의 병목 + 9의 KPI + 캠페인 목표(detected_objective)에서 결정론 규칙으로 파생한다.
from __future__ import annotations

from domain.simulation.contracts.debate_schemas import DebateTopic, ReactionAnalysis
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    PersonaReaction,
    SimulationAggregate,
)
from domain.simulation.tools.aggregation.aggregator import BasicAggregator

# 주신호 판정 임계 — 어느 신호를 토론 초점으로 삼을지 결정(우선순위 순으로 검사).
_REJECTION_TH = 0.3  # 거부율 이 이상이면 거부가 주신호
_TRUST_HIGH = 3.5  # 신뢰 이 이상이면 "신뢰는 확보"
_CLICK_LOW = 0.3  # 클릭 의향 이 미만이면 "행동 안 함"


def compute_kpi(reactions: list[PersonaReaction]) -> SimulationAggregate:
    """4대 KPI 확정 — 기존 가중 집계 엔진 그대로(재현·감사). 더미 aggregate와 일치해야 한다."""
    return BasicAggregator().aggregate(reactions)


def _pct(x: float) -> str:
    return f"{round(x * 100, 1)}%"


def build_topic(
    analysis: ReactionAnalysis,
    agg: SimulationAggregate,
    ad_analysis: AdInterpretation | None = None,
) -> DebateTopic:
    """병목 + KPI + 캠페인 목표 → 토론 주제(결정론).

    주신호 우선순위: 거부 → 신뢰-행동 갭 → 초기이탈(attention병목) → 중간이탈.
    """
    bn = analysis.bottleneck
    objective = ad_analysis.detected_objective if ad_analysis else None

    if agg.rejection_rate >= _REJECTION_TH:
        signal = "rejection"
        diagnosis = f"거부 반응이 큼(거부율 {_pct(agg.rejection_rate)})"
        question = "무엇이 거부를 부르나?"
    elif agg.trust_avg >= _TRUST_HIGH and agg.click_intent_rate < _CLICK_LOW:
        signal = "trust_action_gap"
        click = _pct(agg.click_intent_rate)
        diagnosis = f"신뢰는 높은데(신뢰 {agg.trust_avg}) 클릭이 안 됨(클릭 의향 {click})"
        question = "무엇이 행동을 막나?"
    elif bn is not None and bn.from_stage == "attention":
        signal = "early_attrition"
        diagnosis = f"초반 이탈이 큼({bn.from_stage}→{bn.to_stage} {bn.dropped}명)"
        question = "왜 흥미로 이어지지 않나?"
    else:
        signal = "mid_attrition"
        where = f"{bn.from_stage}→{bn.to_stage} {bn.dropped}명" if bn else "중간 단계"
        diagnosis = f"흥미는 있으나 다음 단계로 안 감({where})"
        question = "무엇이 다음 단계를 막나?"

    return DebateTopic(
        headline=f"{diagnosis} — {question}",
        diagnosis=diagnosis,
        question=question,
        primary_signal=signal,
        focus={
            "bottleneck": f"{bn.from_stage}->{bn.to_stage}" if bn else None,
            "bottleneck_dropped": float(bn.dropped) if bn else None,
            "click_intent_rate": agg.click_intent_rate,
            "trust_avg": agg.trust_avg,
            "rejection_rate": agg.rejection_rate,
        },
        objective=objective,
    )
