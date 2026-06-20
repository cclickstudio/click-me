# 캠페인 목표 달성 가능성(결정론 룰, LLM✗) — 목표별 KPI 가중 조합 → 등급+상대점수+근거.
#
# 시뮬 신호의 '상대적 유리/불리'만 본다. 실측 CTR·확률로 단정 금지(exploratory).
# 입력: 사용자 선언 목표 + 집계(SimulationAggregate) + 반응(PersonaReaction, AISAS 퍼널).
from __future__ import annotations

from collections.abc import Callable

from domain.simulation.contracts.schemas import (
    ObjectiveContribution,
    ObjectiveFit,
    PersonaReaction,
    SimulationAggregate,
)

# 목표 유형 매핑 — 선언 목표 문자열에 키워드가 있으면 해당 유형(부분 일치, 첫 매칭 우선).
# retention을 purchase보다 먼저 둔다 — "재구매"가 "구매"보다 구체적이라 우선 매칭돼야 한다.
_GOAL_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("awareness", ("관심", "인지", "브랜드", "도달", "노출", "상기", "awareness")),
    ("click", ("클릭", "방문", "트래픽", "유입", "click", "traffic")),
    ("lead", ("가입", "문의", "리드", "상담", "신청", "구독", "팔로", "lead")),
    ("retention", ("재구매", "단골", "유지", "리텐션", "충성", "로열", "retention")),
    ("purchase", ("구매", "전환", "결제", "판매", "주문", "purchase", "conversion")),
]

# 유효표본수가 이보다 작으면 신뢰 낮음 경고.
_LOW_CONFIDENCE_N = 10.0

# 등급 임계(상대점수 0~100).
_GRADE_HIGH = 66
_GRADE_MID = 33


def _match_goal(objective: str) -> str:
    text = objective.lower()
    for goal, keywords in _GOAL_KEYWORDS:
        if any(k.lower() in text for k in keywords):
            return goal
    return "general"


def _weighted_rate(
    reactions: list[PersonaReaction], pred: Callable[[PersonaReaction], bool]
) -> float:
    """QA 통과분만, 가중치(weight) 적용한 비율(0~1). 표본 없으면 0."""
    den = sum(r.weight for r in reactions if r.qa_passed)
    if den <= 0:
        return 0.0
    num = sum(r.weight for r in reactions if r.qa_passed and pred(r))
    return num / den


def _grade(score: int) -> str:
    if score >= _GRADE_HIGH:
        return "높음"
    if score >= _GRADE_MID:
        return "보통"
    return "낮음"


def assess_objective_fit(
    objective: str | None,
    aggregate: SimulationAggregate,
    reactions: list[PersonaReaction],
) -> ObjectiveFit | None:
    """선언 목표 + 집계/반응 신호 → 달성 가능성(등급+상대점수+근거). 목표 없으면 None."""
    if not objective or not objective.strip():
        return None

    goal = _match_goal(objective)

    # 정규화 신호(0~1). 1~5 척도는 (x-1)/4, 거부율은 낮을수록 좋으므로 역방향.
    attention = _weighted_rate(reactions, lambda r: r.aisas.attention)
    interest = _weighted_rate(reactions, lambda r: r.aisas.interest)
    search = _weighted_rate(reactions, lambda r: r.aisas.search)
    click_intent = max(0.0, min(1.0, aggregate.click_intent_rate))  # = Action 통과율(가중)
    purchase = max(0.0, min(1.0, (aggregate.purchase_intent - 1.0) / 4.0))
    trust = max(0.0, min(1.0, (aggregate.trust_avg - 1.0) / 4.0))
    low_rejection = max(0.0, min(1.0, 1.0 - aggregate.rejection_rate))
    brand = max(0.0, min(1.0, aggregate.brand_recognition_rate))

    # 목표별 (신호명, 값, 가중치) — 가중치 합 = 1.0.
    weights: dict[str, list[tuple[str, float, float]]] = {
        "awareness": [
            ("주목률", attention, 0.35),
            ("흥미 전환", interest, 0.25),
            ("브랜드 식별률", brand, 0.25),
            ("낮은 거부율", low_rejection, 0.15),
        ],
        "click": [
            ("클릭 의향률", click_intent, 0.60),
            ("정보탐색 전환", search, 0.25),
            ("흥미 전환", interest, 0.15),
        ],
        "lead": [
            ("클릭 의향률", click_intent, 0.40),
            ("정보탐색 전환", search, 0.30),
            ("신뢰도", trust, 0.30),
        ],
        "purchase": [
            ("구매의도", purchase, 0.45),
            ("클릭 의향률", click_intent, 0.35),
            ("신뢰도", trust, 0.20),
        ],
        "retention": [
            ("신뢰도", trust, 0.45),
            ("구매의도", purchase, 0.35),
            ("낮은 거부율", low_rejection, 0.20),
        ],
        "general": [
            ("클릭 의향률", click_intent, 0.25),
            ("구매의도", purchase, 0.25),
            ("신뢰도", trust, 0.25),
            ("낮은 거부율", low_rejection, 0.25),
        ],
    }
    rows = weights[goal]
    score = round(sum(value * weight for _, value, weight in rows) * 100)
    score = max(0, min(100, score))
    grade = _grade(score)

    contributions = [
        ObjectiveContribution(label=label, value=round(value, 3), weight=weight)
        for label, value, weight in rows
    ]
    # 근거 — 가중 기여도 상위(강점)·하위(약점) 신호로 한 줄 구성.
    by_contrib = sorted(rows, key=lambda x: x[1] * x[2], reverse=True)
    top, bottom = by_contrib[0], by_contrib[-1]
    rationale = (
        f"{grade} — '{top[0]}'({top[1]:.0%})이 목표를 뒷받침하고, "
        f"'{bottom[0]}'({bottom[1]:.0%})은 보강이 필요합니다."
    )

    return ObjectiveFit(
        objective=objective.strip(),
        matched_goal=goal,
        score=score,
        grade=grade,
        rationale=rationale,
        contributions=contributions,
        low_confidence=aggregate.effective_n < _LOW_CONFIDENCE_N,
    )
