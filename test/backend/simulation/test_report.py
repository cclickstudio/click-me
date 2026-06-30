# 조각 11 리포트 조립 단위 테스트 — 브랜드 식별(§2-5)·구매의도 분포(§2-2)·루브릭(§4) 적재 검증
from __future__ import annotations

from domain.simulation.contracts.schemas import (
    AdInterpretation,
    Aisas,
    PersonaReaction,
    RubricScore,
)
from domain.simulation.tools.aggregation.aggregator import BasicAggregator
from domain.simulation.tools.debate.analyzer import analyze_reactions
from domain.simulation.tools.debate.kpi import build_topic
from domain.simulation.tools.debate.report import build_report


def _reaction(
    pid: str,
    *,
    action: bool,
    purchase: int,
    brand: bool,
    emotion: str = "curiosity",
    perceived_brand: str | None = None,
) -> PersonaReaction:
    return PersonaReaction(
        persona_id=pid,
        aisas=Aisas(attention=True, interest=True, search=action, action=action),
        purchase_intent=purchase,
        trust=4,
        brand_recognized=brand,
        perceived_brand=perceived_brand,
        emotion_tag=emotion,
    )


_AD = AdInterpretation(
    ad_id="ad-1", detected_message="제로슈거 신제품", detected_industry="beverage"
)

# 5명 — 3명 브랜드 식별(2명은 '신라면'으로 인식), 2명 미식별. 구매의도 1·2·3·3·5.
_REACTIONS = [
    _reaction("P1", action=True, purchase=5, brand=True, perceived_brand="신라면"),
    _reaction("P2", action=True, purchase=3, brand=True, perceived_brand="신라면"),
    _reaction("P3", action=False, purchase=3, brand=True, perceived_brand="진라면"),
    _reaction("P4", action=False, purchase=2, brand=False, emotion="indifference"),
    _reaction("P5", action=False, purchase=1, brand=False, emotion="indifference"),
]


def test_analyzer_emits_purchase_dist_and_brand_breakdown() -> None:
    analysis = analyze_reactions(_REACTIONS, _AD)
    # 구매의도 분포 — 1~5 전 구간 고정, 누락 구간은 0.
    assert analysis.purchase_intent_dist == {1: 1, 2: 1, 3: 2, 4: 0, 5: 1}
    # 브랜드 식별 분해 — 3명 식별 / 2명 미식별, 인식 브랜드명 분포.
    br = analysis.brand_recognition
    assert br is not None
    assert br.recognized_count == 3 and br.unrecognized_count == 2
    assert br.recognition_rate == 0.6
    assert br.perceived_brands == {"신라면": 2, "진라면": 1}


def test_build_report_carries_brand_dist_and_rubric() -> None:
    analysis = analyze_reactions(_REACTIONS, _AD)
    aggregate = BasicAggregator().aggregate(_REACTIONS)
    topic = build_topic(analysis, aggregate, _AD)
    rubric = [
        RubricScore(dimension="cta_clarity", score=41, evidence={"note": "행동 지시 부재"}),
        RubricScore(dimension="hook", score=86, evidence={}),
    ]

    report = build_report(analysis, aggregate, topic, None, rubric)

    # §1 KPI — 브랜드 식별률이 집계값 그대로 실린다.
    assert report.kpi.brand_recognition_rate == aggregate.brand_recognition_rate
    # §2 상세 — 분포·분해가 토론 없이도(공통 필드) 실린다.
    assert report.purchase_intent_dist == analysis.purchase_intent_dist
    assert report.emotion_dist == analysis.emotion_dist
    assert report.brand_recognition is not None and report.brand_recognition.recognized_count == 3
    assert report.rejection is not None
    # §4 루브릭 — 주입한 점수가 그대로 실린다.
    assert [s.dimension for s in report.rubric_scores] == ["cta_clarity", "hook"]
    assert report.debate_available is False


def test_build_report_without_rubric_leaves_diagnosis_empty() -> None:
    analysis = analyze_reactions(_REACTIONS, _AD)
    aggregate = BasicAggregator().aggregate(_REACTIONS)
    topic = build_topic(analysis, aggregate, _AD)

    report = build_report(analysis, aggregate, topic)  # rubric 미주입

    assert report.rubric_scores == []
    assert report.brand_recognition is not None  # §2 데이터는 루브릭과 무관하게 실린다
