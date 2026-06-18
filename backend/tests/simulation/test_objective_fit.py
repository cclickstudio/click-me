# 캠페인 목표 달성 가능성(결정론 룰) 단위 테스트 — 매핑·점수·등급·신뢰도.
from domain.simulation.contracts.schemas import (
    Aisas,
    PersonaReaction,
    SimulationAggregate,
)
from domain.simulation.tools.objective_fit import assess_objective_fit


def _agg(**kw) -> SimulationAggregate:
    base = {
        "click_intent_rate": 0.4,
        "ci_low": 0.3,
        "ci_high": 0.5,
        "purchase_intent": 3.5,
        "trust_avg": 4.0,
        "rejection_rate": 0.2,
        "brand_recognition_rate": 0.7,
        "effective_n": 18.0,
    }
    base.update(kw)
    return SimulationAggregate(**base)


def _react(pid, att, intr, srch, act, *, qa=True, w=1.0) -> PersonaReaction:
    return PersonaReaction(
        persona_id=pid,
        aisas=Aisas(attention=att, interest=intr, search=srch, action=act),
        purchase_intent=3,
        trust=4,
        qa_passed=qa,
        weight=w,
    )


_REACTIONS = [
    _react("p1", True, True, True, True),
    _react("p2", True, True, False, False),
    _react("p3", True, False, False, False),
    _react("p4", True, True, True, False),
    _react("p5", False, False, False, False),
]


def test_objective_none_or_blank_returns_none():
    assert assess_objective_fit(None, _agg(), _REACTIONS) is None
    assert assess_objective_fit("   ", _agg(), _REACTIONS) is None


def test_goal_keyword_mapping():
    cases = {
        "관심 유도": "awareness",
        "클릭 유도": "click",
        "가입·문의 유도": "lead",
        "구매 전환": "purchase",
        "재구매·단골": "retention",
        "우리만의 독특한 목표": "general",
    }
    for objective, expected in cases.items():
        fit = assess_objective_fit(objective, _agg(), _REACTIONS)
        assert fit is not None
        assert fit.matched_goal == expected


def test_score_bounds_and_grade_consistency():
    fit = assess_objective_fit("클릭 유도", _agg(), _REACTIONS)
    assert fit is not None
    assert 0 <= fit.score <= 100
    if fit.score >= 66:
        assert fit.grade == "높음"
    elif fit.score >= 33:
        assert fit.grade == "보통"
    else:
        assert fit.grade == "낮음"
    # 기여 신호 가중치 합 = 1.0(구성 검증).
    assert abs(sum(c.weight for c in fit.contributions) - 1.0) < 1e-6
    assert fit.exploratory is True


def test_high_signals_score_higher_than_low():
    strong = _agg(click_intent_rate=0.9, purchase_intent=5.0, trust_avg=5.0, rejection_rate=0.0)
    weak = _agg(click_intent_rate=0.05, purchase_intent=1.0, trust_avg=1.0, rejection_rate=0.9)
    hi = assess_objective_fit("구매 전환", strong, _REACTIONS)
    lo = assess_objective_fit("구매 전환", weak, _REACTIONS)
    assert hi is not None and lo is not None
    assert hi.score > lo.score


def test_low_confidence_flag_on_small_effective_n():
    small = assess_objective_fit("클릭 유도", _agg(effective_n=5.0), _REACTIONS)
    big = assess_objective_fit("클릭 유도", _agg(effective_n=50.0), _REACTIONS)
    assert small is not None and big is not None
    assert small.low_confidence is True
    assert big.low_confidence is False


def test_deterministic():
    a = assess_objective_fit("관심 유도", _agg(), _REACTIONS)
    b = assess_objective_fit("관심 유도", _agg(), _REACTIONS)
    assert a == b
