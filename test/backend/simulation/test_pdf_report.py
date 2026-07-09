# PDF 리포트 렌더 테스트 — reportlab 바이트 생성·한글 깨짐 없이 빌드 완료 검증
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
from domain.simulation.tools.debate.pdf_report import (
    MIN_SEGMENT_CELL_SIZE,
    _overall,
    _segments_qualify,
    render_report_pdf,
)
from domain.simulation.tools.debate.report import build_report

_AD = AdInterpretation(
    ad_id="ad-1", detected_message="제로슈거 신제품", detected_industry="beverage"
)
_REACTIONS = [
    PersonaReaction(
        persona_id=f"P{i}",
        aisas=Aisas(attention=True, interest=i % 2 == 0, action=i % 3 == 0),
        purchase_intent=(i % 5) + 1,
        trust=4,
        brand_recognized=i % 2 == 0,
        perceived_brand="신라면" if i % 2 == 0 else None,
        rejected=i % 4 == 0,
        emotion_tag="curiosity",
    )
    for i in range(6)
]


def _result(*, with_rubric: bool) -> dict:
    analysis = analyze_reactions(_REACTIONS, _AD)
    aggregate = BasicAggregator().aggregate(_REACTIONS)
    topic = build_topic(analysis, aggregate, _AD)
    rubric = [RubricScore(dimension="cta_clarity", score=41, evidence={})] if with_rubric else None
    report = build_report(analysis, aggregate, topic, None, rubric)
    return {
        "run_id": "run-1",
        "ad_analysis": _AD.model_dump(),
        "analysis": analysis.model_dump(),
        "aggregate": aggregate.model_dump(),
        "topic": topic.model_dump(),
        "report": report.model_dump(),
    }


def test_pdf_is_generated_with_korean_sections() -> None:
    pdf = render_report_pdf(_result(with_rubric=True))
    assert pdf[:4] == b"%PDF"  # PDF 매직넘버
    assert len(pdf) > 1500  # 빈 문서가 아니라 섹션이 실제로 렌더됨


def test_pdf_renders_without_rubric() -> None:
    # 루브릭 미주입(토론 미실행 유사)에도 §2 데이터로 빌드가 완료돼야 한다.
    pdf = render_report_pdf(_result(with_rubric=False))
    assert pdf[:4] == b"%PDF"


def test_pdf_handles_empty_result() -> None:
    # 방어 — 빈 result여도 예외 없이 최소 문서를 만든다.
    pdf = render_report_pdf({})
    assert pdf[:4] == b"%PDF"


def test_overall_excludes_brand_recognition() -> None:
    # T3 — 브랜드 식별률은 품질 지표가 아니므로 종합 점수 산식에서 제외한다(리포트엔 별도 표시).
    # 브랜드 식별률만 다르고 나머지가 같으면 종합 점수가 동일해야 한다.
    base = {
        "click_intent_rate": 0.2,
        "purchase_intent": 3.0,
        "trust_avg": 4.0,
        "rejection_rate": 0.1,
    }
    low_brand = {**base, "brand_recognition_rate": 0.0}
    high_brand = {**base, "brand_recognition_rate": 0.9}
    assert _overall(low_brand, []) == _overall(high_brand, [])
    # 4개 지표(클릭·구매/5·신뢰/5·거부↓)의 평균×100
    expected = round((0.2 + 3.0 / 5 + 4.0 / 5 + (1 - 0.1)) / 4 * 100)
    assert _overall(high_brand, []) == expected


def test_segments_qualify_threshold() -> None:
    # T4 — 유효표본 20명 이상 셀이 하나라도 있어야 세그먼트 섹션을 출력한다(작은 표본 노이즈 차단).
    assert MIN_SEGMENT_CELL_SIZE == 20
    assert _segments_qualify([{"effective_n": 20.0}]) is True
    assert _segments_qualify([{"effective_n": 24.0}, {"effective_n": 3.0}]) is True
    assert _segments_qualify([{"effective_n": 19.9}, {"effective_n": 5.0}]) is False
    assert _segments_qualify([]) is False  # 셀 없음도 미달로 취급
