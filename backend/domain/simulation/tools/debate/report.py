# 조각 11 — 리포트 조립(결정론, LLM✗). [KPI(9) + 분석(8) + 토론 결론·발언 인용(10)]을 합친다.
#
# 새로 지어내지 않고 앞 조각 산출을 매핑만 한다. 토론(10-c) 없으면 KPI·분석만 채우고 진단은 주제로.
# 매핑 규칙: docs/simulation/debate/persona-debate-pipeline.md §4
from __future__ import annotations

import re
from collections import Counter

from domain.simulation.contracts.debate_schemas import (
    ConfidenceBadge,
    ContributionBar,
    ConversionStep,
    DebateDigest,
    DebateResult,
    DebateTopic,
    GroupProfile,
    ReactionAnalysis,
    ReportKpi,
    ReportQuote,
    ReportView,
    SegmentCell,
    SimulationReport,
    SummaryMetrics,
)
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    ObjectiveFit,
    Persona,
    PersonaReaction,
    RubricScore,
    SimulationAggregate,
)
from domain.simulation.tools.aggregation.aggregator import _effective_n, _wmean


def _consumer_group_counts(analysis: ReactionAnalysis) -> dict[str, int]:
    g = analysis.groups
    return {
        "finishers": len(g.finishers),
        "undecided": len(g.undecided),
        "rejectors": len(g.rejectors),
        "distrusters": len(g.distrusters),
        "early_drop": len(g.early_drop),
    }


def _quotes(debate: DebateResult, limit: int = 2) -> list[ReportQuote]:
    """결론을 가장 잘 보여주는 대표 발언 1~2개 — 다수 입장 1 + 반대 입장 1(대립의 생생함).

    전문을 싣지 않고 핵심만 인용해 분량을 줄인다(나머지 발언은 토론 전체 debate에만 남는다).
    """
    lasts = [(p, p.utterances[-1]) for p in debate.participants if p.utterances]
    if not lasts:
        return []
    majority = Counter(u.stance for _, u in lasts).most_common(1)[0][0]
    picks: list[tuple] = []
    maj = next(((p, u) for p, u in lasts if u.stance == majority), None)
    if maj:
        picks.append(maj)
    opp = next(((p, u) for p, u in lasts if u.stance != majority), None)
    if opp:
        picks.append(opp)
    return [
        ReportQuote(
            persona_name=p.persona_name,
            role=p.role,
            stance=u.stance,
            text=u.text,
            reason=u.reason,
        )
        for p, u in picks[:limit]
    ]


def build_debate_digest(
    topic: DebateTopic, debate: DebateResult, debate_id: str | None = None
) -> DebateDigest:
    """토론 1건 → 합산 리포트용 요약(주제 + 결론 + 대표 인용 1~2). 전문은 버린다."""
    final = debate.final
    return DebateDigest(
        debate_id=debate_id,
        topic_headline=topic.headline,
        diagnosis=topic.diagnosis,
        rounds_run=debate.rounds_run,
        stop_reason=debate.stop_reason,
        consensus=final.consensus if final else [],
        dissent=final.dissent if final else [],
        ranked_actions=final.ranked_actions if final else [],
        quotes=_quotes(debate),
    )


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


# ── 통합 ReportView 조립 — 시뮬+토론 종합(결정론, LLM✗) ──

# 연령 버킷 경계(상한 미만) — 그 외는 60대+.
_AGE_BANDS: list[tuple[int, str]] = [
    (20, "10대"),
    (30, "20대"),
    (40, "30대"),
    (50, "40대"),
    (60, "50대"),
]
_POS_EMO = ("curiosity", "delight", "empathy", "trust")
_NEG_EMO = ("annoyance", "distrust")


def _age_band(age: int) -> str:
    for hi, label in _AGE_BANDS:
        if age < hi:
            return label
    return "60대+"


def _gint(d: dict, key: int) -> int:
    """int/str 키 혼용(JSON 직렬화 후) 모두 대응."""
    return int(d.get(key, d.get(str(key), 0)))


def _segment_breakdown(
    personas: list[Persona], reactions: list[PersonaReaction]
) -> list[SegmentCell]:
    """personas×reactions 조인 → 연령대×성별 셀별 가중 KPI 재집계(최대 차별점)."""
    rmap = {r.persona_id: r for r in reactions if r.qa_passed}
    cells: dict[tuple[str, str], list[PersonaReaction]] = {}
    for p in personas:
        r = rmap.get(p.persona_id)
        if r is None:
            continue
        cells.setdefault((_age_band(p.age), p.gender), []).append(r)
    out: list[SegmentCell] = []
    for (band, gender), rs in cells.items():
        w = [float(x.weight) for x in rs]
        eff = _effective_n(w)
        out.append(
            SegmentCell(
                age_band=band,
                gender=gender,
                n=len(rs),
                effective_n=round(eff, 1),
                click_intent_rate=round(_wmean([float(x.aisas.action) for x in rs], w), 4),
                purchase_intent=round(_wmean([float(x.purchase_intent) for x in rs], w), 2),
                trust_avg=round(_wmean([float(x.trust) for x in rs], w), 2),
                rejection_rate=round(_wmean([float(x.rejected) for x in rs], w), 4),
                attention_pass_rate=round(_wmean([float(x.aisas.attention) for x in rs], w), 4),
                low_confidence=eff < 10,
            )
        )
    # 인원 많은 셀부터 — 화면 테이블·PDF(_segment_block) 정렬과 통일(과신 방지 정렬).
    out.sort(key=lambda c: c.n, reverse=True)
    return out


def _group_profiles(
    analysis: ReactionAnalysis, personas: list[Persona], reactions: list[PersonaReaction]
) -> dict[str, GroupProfile]:
    """소비자 그룹별 인구통계 프로필 — 누가 완주하고 누가 떠나나(겹침 허용)."""
    pmap = {p.persona_id: p for p in personas}
    emo = {r.persona_id: str(r.emotion_tag) for r in reactions}
    g = analysis.groups
    groups = {
        "finishers": g.finishers,
        "undecided": g.undecided,
        "rejectors": g.rejectors,
        "distrusters": g.distrusters,
        "early_drop": g.early_drop,
    }
    out: dict[str, GroupProfile] = {}
    for name, ids in groups.items():
        ps = [pmap[i] for i in ids if i in pmap]
        if not ps:
            out[name] = GroupProfile(count=len(ids), avg_age=0.0)
            continue
        n = len(ps)
        gc = Counter(p.gender for p in ps)
        ec = Counter(emo[i] for i in ids if i in emo)
        out[name] = GroupProfile(
            count=len(ids),
            avg_age=round(sum(p.age for p in ps) / n, 1),
            gender_ratio={k: round(v / n, 3) for k, v in gc.items()},
            top_emotion=(ec.most_common(1)[0][0] if ec else None),
        )
    return out


def _target_match(detected: str, perceived: str) -> bool:
    d = set(re.findall(r"\w+", detected.lower()))
    p = set(re.findall(r"\w+", perceived.lower()))
    return bool(d & p)


def _summary_metrics(
    analysis: ReactionAnalysis,
    aggregate: SimulationAggregate,
    objective_fit: ObjectiveFit | None,
    ad_analysis: AdInterpretation | None,
    reactions: list[PersonaReaction],
    report: SimulationReport,
) -> SummaryMetrics:
    """분포 기반 파생 요약 — Top2box·감정비율·신뢰행동갭·기여·전환·타깃·할인(평균 단언 회피)."""
    pid = analysis.purchase_intent_dist or {}
    ptot = sum(pid.values()) or 1
    top2 = (_gint(pid, 4) + _gint(pid, 5)) / ptot
    bot2 = (_gint(pid, 1) + _gint(pid, 2)) / ptot

    emo = analysis.emotion_dist or {}
    etot = sum(emo.values()) or 1
    pos = sum(emo.get(k, 0) for k in _POS_EMO) / etot
    neg = sum(emo.get(k, 0) for k in _NEG_EMO) / etot
    neu = max(0.0, 1.0 - pos - neg)

    gap = aggregate.trust_avg - aggregate.click_intent_rate * 5
    gap_label = "믿는데 안 누름" if gap > 0.5 else "안 믿는데 누름" if gap < -0.5 else "균형"

    waterfall: list[ContributionBar] = []
    weakest: str | None = None
    if objective_fit and objective_fit.contributions:
        bars = sorted(objective_fit.contributions, key=lambda c: c.value * c.weight, reverse=True)
        waterfall = [
            ContributionBar(
                label=c.label,
                contribution=round(c.value * c.weight, 4),
                value=c.value,
                weight=c.weight,
            )
            for c in bars
        ]
        weakest = bars[-1].label
    linked = report.ranked_actions[0].rank if (weakest and report.ranked_actions) else None

    fconv: list[ConversionStep] = []
    fn = analysis.funnel or []
    for a, b in zip(fn, fn[1:], strict=False):
        if a.passed > 0:
            fconv.append(
                ConversionStep(
                    from_stage=a.stage, to_stage=b.stage, conversion=round(b.passed / a.passed, 4)
                )
            )

    tm: float | None = None
    if ad_analysis and ad_analysis.detected_target:
        passed = [r for r in reactions if r.qa_passed and r.perceived_target]
        if passed:
            m = sum(
                1 for r in passed if _target_match(ad_analysis.detected_target, r.perceived_target)
            )
            tm = round(m / len(passed), 4)

    disc: float | None = None
    if ad_analysis:
        f = ad_analysis.ad_features
        if f and f.original_price and f.discounted_price and f.original_price > 0:
            disc = round(1 - f.discounted_price / f.original_price, 3)

    return SummaryMetrics(
        top2box_purchase=round(top2, 4),
        bottom2box_purchase=round(bot2, 4),
        positive_emotion_rate=round(pos, 4),
        negative_emotion_rate=round(neg, 4),
        neutral_emotion_rate=round(neu, 4),
        trust_action_gap=round(gap, 2),
        trust_action_label=gap_label,
        contribution_waterfall=waterfall,
        weakest_signal=weakest,
        weakest_linked_action_rank=linked,
        funnel_conversion=fconv,
        target_match_rate=tm,
        discount_rate=disc,
    )


def _confidence_badge(
    aggregate: SimulationAggregate, objective_fit: ObjectiveFit | None, total_n: int
) -> ConfidenceBadge:
    """전 섹션 공통 신뢰 배지 — CI 폭·유효표본·경고 문구(실측 환산 금지 포함)."""
    ciw = aggregate.ci_high - aggregate.ci_low
    low_conf = bool(objective_fit and objective_fit.low_confidence)
    warnings: list[str] = []
    if aggregate.variance_warning:
        warnings.append("응답 동질화 의심(분산 낮음) — 재시뮬 권장")
    if low_conf or aggregate.effective_n < 10:
        warnings.append("유효표본 부족 — 표본 늘려 재시뮬 권장")
    warnings.append("실측 보정 전(exploratory) — 실측 CTR 등 실측 스케일 환산 금지")
    if aggregate.effective_n < 10 or low_conf:
        level = "low"
    elif aggregate.variance_warning or ciw > 0.25:
        level = "medium"
    else:
        level = "high"
    return ConfidenceBadge(
        level=level,
        ci_width=round(ciw, 4),
        effective_n=aggregate.effective_n,
        total_n=total_n,
        warnings=warnings,
    )


def build_report_view(
    *,
    run_id: str,
    simulation_id: str | None,
    debate_id: str | None,
    report: SimulationReport,
    objective_fit: ObjectiveFit | None,
    ad_analysis: AdInterpretation | None,
    ad: dict | None,
    topic: DebateTopic | None,
    debate: DebateResult | None,
    aggregate: SimulationAggregate,
    analysis: ReactionAnalysis,
    personas: list[Persona],
    reactions: list[PersonaReaction],
    generated_at: str,
    debates: list[DebateDigest] | None = None,
) -> ReportView:
    """시뮬+토론 산출을 단일 ReportView로 종합 — 화면·PDF 공용 진실 소스(결정론, LLM✗).

    대부분 매핑이고, segments·group_profiles·summary_metrics·confidence만 신규 파생.
    message_reception은 analysis.message를 최상위로 승격(기존 리포트서 누락된 1순위 데이터).
    """
    return ReportView(
        run_id=run_id,
        simulation_id=simulation_id,
        debate_id=debate_id,
        report=report,
        objective_fit=objective_fit,
        ad_analysis=ad_analysis,
        ad=ad,
        topic=topic,
        segments=_segment_breakdown(personas, reactions),
        group_profiles=_group_profiles(analysis, personas, reactions),
        message_reception=analysis.message,
        summary_metrics=_summary_metrics(
            analysis, aggregate, objective_fit, ad_analysis, reactions, report
        ),
        confidence=_confidence_badge(aggregate, objective_fit, analysis.total_n),
        debate=debate,
        debates=debates or [],
        aggregate=aggregate,
        analysis=analysis,
        generated_at=generated_at,
    )
