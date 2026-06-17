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
_RESIST_TH = 0.5  # 메시지 저항률 이 이상이면 "메시지가 안 먹힘"이 주신호
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

    주신호 우선순위: 거부 → 메시지 갭 → 신뢰-행동 갭 → 초기이탈(attention병목) → 중간이탈.
    """
    bn = analysis.bottleneck
    objective = ad_analysis.detected_objective if ad_analysis else None
    msg = analysis.message

    if agg.rejection_rate >= _REJECTION_TH:
        signal = "rejection"
        diagnosis = f"거부 반응이 큼(거부율 {_pct(agg.rejection_rate)})"
        question = "무엇이 거부를 부르나?"
    elif msg is not None and msg.resistance_rate >= _RESIST_TH:
        signal = "message_gap"
        diagnosis = f"의도 메시지가 잘 안 먹힘(저항 {_pct(msg.resistance_rate)})"
        question = "메시지의 무엇이 받아들여지지 않나?"
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
            "message_resistance_rate": msg.resistance_rate if msg else None,
        },
        objective=objective,
    )


# 신호 강도 정규화 기준 — strength(0~1) 산출용. 임계(_TH)보다 큰 정도를 0~1로 환산.
# confidence = strength(수치가 임계를 얼마나 넘었나), ranking = strength 내림차순 1~5.
_REJECTION_FULL = 0.6  # 거부율 이 이상이면 강도 1.0(거부 신호 포화)
_RESIST_FULL = 0.8  # 메시지 저항률 이 이상이면 강도 1.0
_GAP_FULL = 2.5  # 신뢰-클릭 갭(신뢰점수 − 클릭의향*5 환산)의 포화점
_DROP_FULL = 0.6  # 단계 이탈률(drop_rate) 이 이상이면 강도 1.0


def _strength(value: float, lo: float, hi: float) -> float:
    """value를 [lo, hi] 구간에서 0~1로 정규화(범위 밖은 클램프). 신호 강도 환산용."""
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def build_topic_candidates(
    analysis: ReactionAnalysis,
    agg: SimulationAggregate,
    ad_analysis: AdInterpretation | None = None,
) -> list[DebateTopic]:
    """추가 토론용 논제 후보 5개(결정론·LLM✗) — 5가지 주신호를 모두 진단형 대립 논제로.

    각 후보는 '선택을 강요'하지 않고 대립 가능한 쟁점을 진단형으로 던진다(변경2·4 일관).
    강도(수치가 임계를 얼마나 넘었나)로 confidence·ranking을 채워 정렬한다. 모든 문구·수치는
    실제 analysis/agg에 grounded(수치 밖 지어내기 금지). 신호가 약해도 5개를 모두 반환한다.
    """
    # 주체명 — 카테고리/산업/제품명을 논제 문장 주어로(없으면 '이 광고'). 지어내지 않음.
    subject = _subject_name(ad_analysis)
    bn = analysis.bottleneck
    objective = ad_analysis.detected_objective if ad_analysis else None
    msg = analysis.message
    resist = msg.resistance_rate if msg else 0.0

    # 신뢰-행동 갭: 신뢰(1~5)와 클릭의향(0~1 → 5점 환산)의 차. 신뢰 높고 클릭 낮을수록 큼.
    trust_action_gap = agg.trust_avg - agg.click_intent_rate * 5.0
    drop_rate = bn.drop_rate if bn else 0.0
    bn_where = f"{bn.from_stage}→{bn.to_stage} {bn.dropped}명" if bn else "중간 단계"
    click_pct = _pct(agg.click_intent_rate)
    is_early = bn is not None and bn.from_stage == "attention"
    # 초기/중간 이탈은 같은 병목을 두 관점으로 본다 — 병목이 attention이면 초기, 아니면 중간이 강함.
    early_strength = _strength(drop_rate, 0.2, _DROP_FULL) if is_early else 0.0
    mid_strength = _strength(drop_rate, 0.2, _DROP_FULL) if not is_early else 0.0

    specs: list[tuple[str, str, str, float]] = [
        (
            "rejection",
            f"{subject}는 메시지를 바꿔야 하는가, 타깃을 바꿔야 하는가",
            f"거부 반응이 큼(거부율 {_pct(agg.rejection_rate)})",
            _strength(agg.rejection_rate, _REJECTION_TH, _REJECTION_FULL),
        ),
        (
            "message_gap",
            f"{subject}의 메시지를 새로 써야 하는가, 표현만 다듬으면 되는가",
            f"의도 메시지가 잘 안 먹힘(저항 {_pct(resist)})",
            _strength(resist, _RESIST_TH, _RESIST_FULL),
        ),
        (
            "trust_action_gap",
            f"{subject}는 행동 유도(CTA)를 강화해야 하는가, 동기(혜택)를 더 줘야 하는가",
            f"신뢰는 높은데(신뢰 {agg.trust_avg}) 클릭이 안 됨(클릭 의향 {click_pct})",
            _strength(trust_action_gap, 0.5, _GAP_FULL),
        ),
        (
            "early_attrition",
            f"{subject}는 초반 후킹을 바꿔야 하는가, 노출 맥락(매체·타깃)을 바꿔야 하는가",
            f"초반 이탈이 큼({bn_where})" if is_early else f"초반 통과는 됨({bn_where})",
            early_strength,
        ),
        (
            "mid_attrition",
            f"{subject}는 다음 단계 진입 이유(혜택)를 줘야 하는가, 경로(흐름)를 단순화해야 하는가",
            f"흥미는 있으나 다음 단계로 안 감({bn_where})"
            if not is_early
            else f"중간 단계는 유지됨({bn_where})",
            mid_strength,
        ),
    ]

    # 강도 내림차순 정렬 → ranking 1~5 부여(동률은 spec 정의 순으로 안정 정렬).
    ordered = sorted(enumerate(specs), key=lambda it: (-it[1][3], it[0]))
    topics: list[DebateTopic] = []
    for rank, (_, (signal, headline, diagnosis, strength)) in enumerate(ordered, start=1):
        topics.append(
            DebateTopic(
                headline=headline,
                diagnosis=diagnosis,
                question=headline,  # 진단형 논제 자체가 질문(이분법 '선택' 강요 아님)
                primary_signal=signal,
                focus={
                    "bottleneck": f"{bn.from_stage}->{bn.to_stage}" if bn else None,
                    "bottleneck_dropped": float(bn.dropped) if bn else None,
                    "click_intent_rate": agg.click_intent_rate,
                    "trust_avg": agg.trust_avg,
                    "rejection_rate": agg.rejection_rate,
                    "message_resistance_rate": resist if msg else None,
                },
                objective=objective,
                topic_id=signal,  # 신호 종류가 곧 후보 식별자(start로 그대로 매칭)
                ranking=rank,
                confidence=round(strength, 3),
            )
        )
    return topics


def _subject_name(ad_analysis: AdInterpretation | None) -> str:
    """논제 문장 주어 — 산업/카테고리명(있으면). 없으면 '이 광고'(지어내지 않음)."""
    if ad_analysis is None:
        return "이 광고"
    detail = ad_analysis.mismatch_detail or {}
    cat = detail.get("category") if isinstance(detail, dict) else None
    declared = cat.get("declared") if isinstance(cat, dict) else None
    return declared or ad_analysis.detected_industry or "이 광고"
