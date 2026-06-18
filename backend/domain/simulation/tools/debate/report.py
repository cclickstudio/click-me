# 조각 11 — 리포트 조립(결정론, LLM✗). [KPI(9) + 분석(8) + 토론 결론·발언 인용(10)]을 합친다.
#
# 새로 지어내지 않고 앞 조각 산출을 매핑만 한다. 토론(10-c) 없으면 KPI·분석만 채우고 진단은 주제로.
# 매핑 규칙: docs/simulation/debate/persona-debate-pipeline.md §4
from __future__ import annotations

from domain.simulation.contracts.debate_schemas import (
    DebateResult,
    DebateTopic,
    ReactionAnalysis,
    ReportKpi,
    ReportQuote,
    SimulationReport,
)
from domain.simulation.contracts.schemas import RubricScore, SimulationAggregate


def _consumer_group_counts(analysis: ReactionAnalysis) -> dict[str, int]:
    g = analysis.groups
    return {
        "finishers": len(g.finishers),
        "undecided": len(g.undecided),
        "rejectors": len(g.rejectors),
        "distrusters": len(g.distrusters),
        "early_drop": len(g.early_drop),
    }


def _quotes(debate: DebateResult) -> list[ReportQuote]:
    """참가자별 대표 발언 1건(마지막 라운드) — 리포트 '실제 소비자 목소리'."""
    quotes = []
    for p in debate.participants:
        if not p.utterances:
            continue
        last = p.utterances[-1]
        quotes.append(
            ReportQuote(
                persona_name=p.persona_name, role=p.role, stance=last.stance, text=last.text
            )
        )
    return quotes


def build_report(
    analysis: ReactionAnalysis,
    aggregate: SimulationAggregate,
    topic: DebateTopic,
    debate: DebateResult | None = None,
    rubric: list[RubricScore] | None = None,
) -> SimulationReport:
    """앞 조각 산출을 리포트로 조립. debate가 None이면 토론 파트는 비우고 진단은 주제로 대체.

    rubric(§4 루브릭 평가 패스)이 주입되면 크리에이티브 진단 점수를 그대로 싣는다(없으면 생략).
    """
    kpi = ReportKpi(
        click_intent_rate=aggregate.click_intent_rate,
        ci_low=aggregate.ci_low,
        ci_high=aggregate.ci_high,
        purchase_intent=aggregate.purchase_intent,
        trust_avg=aggregate.trust_avg,
        rejection_rate=aggregate.rejection_rate,
        brand_recognition_rate=aggregate.brand_recognition_rate,
        variance_warning=aggregate.variance_warning,
        effective_n=aggregate.effective_n,
    )

    # §2 반응 집계 상세·§4 루브릭은 토론 유무와 무관하게 동일하게 싣는다(이미 산출된 데이터).
    common = {
        "topic": topic.headline,
        "kpi": kpi,
        "funnel": analysis.funnel,
        "bottleneck": analysis.bottleneck,
        "purchase_intent_dist": analysis.purchase_intent_dist,
        "rejection": analysis.rejection,
        "by_drop_reason_tag": analysis.by_drop_reason_tag,
        "emotion_dist": analysis.emotion_dist,
        "brand_recognition": analysis.brand_recognition,
        "rubric_scores": rubric or [],
        "consumer_groups": _consumer_group_counts(analysis),
    }

    if debate is not None and debate.final is not None:
        final = debate.final
        return SimulationReport(
            headline=final.headline,
            plain_summary=final.plain_summary,
            debate_available=True,
            rounds_run=debate.rounds_run,
            stop_reason=debate.stop_reason,
            consensus=final.consensus,
            dissent=final.dissent,
            ranked_actions=final.ranked_actions,
            quotes=_quotes(debate),
            **common,
        )

    # 토론 미실행 — KPI·분석만, 진단은 주제 diagnosis로.
    return SimulationReport(headline=topic.diagnosis, debate_available=False, **common)
