# 통합 ReportView 조립 단위 테스트 — 세그먼트·그룹·요약 파생·신뢰 배지·objective_fit 승격 검증
from __future__ import annotations

from domain.simulation.contracts.schemas import (
    AdInterpretation,
    Aisas,
    ObjectiveContribution,
    ObjectiveFit,
    Persona,
    PersonaReaction,
    RubricScore,
)
from domain.simulation.tools.aggregation.aggregator import BasicAggregator
from domain.simulation.tools.debate.analyzer import analyze_reactions
from domain.simulation.tools.debate.kpi import build_topic
from domain.simulation.tools.debate.report import build_report, build_report_view

_AD = AdInterpretation(
    ad_id="ad-1",
    detected_message="제로슈거 신제품",
    detected_industry="음료",
    detected_target="20대 여성",
)
_PERSONAS = [
    Persona(persona_id="P1", age=24, gender="F", region="서울", ocean={}),
    Persona(persona_id="P2", age=27, gender="F", region="서울", ocean={}),
    Persona(persona_id="P3", age=33, gender="M", region="경기", ocean={}),
    Persona(persona_id="P4", age=45, gender="M", region="부산", ocean={}),
    Persona(persona_id="P5", age=22, gender="M", region="서울", ocean={}),
]


def _r(pid, *, action, purchase, brand, emotion="curiosity", rejected=False, ptarget=None):
    return PersonaReaction(
        persona_id=pid,
        aisas=Aisas(attention=True, interest=True, search=action, action=action),
        purchase_intent=purchase,
        trust=4,
        brand_recognized=brand,
        emotion_tag=emotion,
        rejected=rejected,
        perceived_target=ptarget,
    )


_REACTIONS = [
    _r("P1", action=True, purchase=5, brand=True, ptarget="20대 여성"),
    _r("P2", action=True, purchase=4, brand=True, ptarget="젊은 여성"),
    _r("P3", action=False, purchase=3, brand=False, emotion="indifference"),
    _r("P4", action=False, purchase=2, brand=False, emotion="annoyance", rejected=True),
    _r("P5", action=False, purchase=1, brand=True, emotion="distrust"),
]


def _view(*, with_of: bool = True):
    analysis = analyze_reactions(_REACTIONS, _AD)
    agg = BasicAggregator().aggregate(_REACTIONS)
    topic = build_topic(analysis, agg, _AD)
    rubric = [
        RubricScore(dimension="cta_clarity", score=41, evidence={}),
        RubricScore(dimension="hook", score=84, evidence={}),
    ]
    report = build_report(analysis, agg, topic, None, rubric)
    of = (
        ObjectiveFit(
            objective="구매 전환",
            matched_goal="purchase",
            score=55,
            grade="보통",
            rationale="보통 — ...",
            contributions=[
                ObjectiveContribution(label="구매의도", value=0.5, weight=0.45),
                ObjectiveContribution(label="클릭 의향률", value=0.4, weight=0.35),
                ObjectiveContribution(label="신뢰도", value=0.75, weight=0.2),
            ],
        )
        if with_of
        else None
    )
    return build_report_view(
        run_id="r1",
        simulation_id=None,
        debate_id=None,
        report=report,
        objective_fit=of,
        ad_analysis=_AD,
        ad=None,
        topic=topic,
        debate=None,
        aggregate=agg,
        analysis=analysis,
        personas=_PERSONAS,
        reactions=_REACTIONS,
        generated_at="2026-06-18T00:00:00Z",
    )


def test_segments_grouped_by_age_gender():
    v = _view()
    keys = {(s.age_band, s.gender) for s in v.segments}
    assert ("20대", "F") in keys and ("20대", "M") in keys
    assert ("30대", "M") in keys and ("40대", "M") in keys
    f20 = next(s for s in v.segments if s.age_band == "20대" and s.gender == "F")
    assert f20.n == 2 and f20.click_intent_rate == 1.0  # P1·P2 둘 다 action


def test_summary_metrics_derived():
    sm = _view().summary_metrics
    assert sm.top2box_purchase == 0.4  # 구매의도 4·5점 = 2/5
    assert sm.bottom2box_purchase == 0.4  # 1·2점 = 2/5
    assert sm.contribution_waterfall  # objective_fit 있으면 채워짐
    assert sm.weakest_signal is not None
    assert sm.target_match_rate is not None  # detected_target 존재
    assert sm.funnel_conversion  # 인접 단계 전환율


def test_message_and_confidence_and_groups():
    v = _view()
    assert v.message_reception is not None  # analysis.message 최상위 승격
    assert v.confidence.level in ("high", "medium", "low")
    assert any("실측" in w for w in v.confidence.warnings)
    assert "rejectors" in v.group_profiles  # 소비자 그룹 프로필
    assert v.group_profiles["finishers"].count == 2  # P1·P2 action


def test_no_objective_fit_is_safe():
    v = _view(with_of=False)
    assert v.objective_fit is None
    assert v.summary_metrics.contribution_waterfall == []
    assert v.summary_metrics.weakest_signal is None
