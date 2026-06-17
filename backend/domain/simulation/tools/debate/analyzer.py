# 조각 8 — 반응 분석(결정론, LLM✗). reactions[] → 구조적 분석(어디서·왜 새나, 누가 어떤 무리)
#
# 단순 평균이 아니라 퍼널·병목·이탈/거부 분해·소비자 그룹을 산출. 숫자 평균(KPI)은 조각 9.
# qa_passed 표본만 집계. 같은 더미 → 항상 같은 결과(재현·감사 가능).
from __future__ import annotations

from collections import Counter

from domain.simulation.contracts.debate_schemas import (
    AISAS_STAGES,
    Bottleneck,
    FunnelStage,
    GroupMembers,
    MessageReception,
    ReactionAnalysis,
    RejectionBreakdown,
)
from domain.simulation.contracts.schemas import AdInterpretation, PersonaReaction

# 메시지 저항 신호어(한국어 광고 반응) — 의도 메시지에 대한 과장·식상·무관심 표현.
# 결정론 사전이라 거칠다(해석은 토론이 보완). 케이스 누적되면 보강.
_RESISTANCE_TERMS = [
    "과장",
    "오버",
    "오바",
    "글쎄",
    "모르겠",
    "아니냐",
    "아니야",  # 과장·회의
    "늘 먹던",
    "맨날",
    "딱히",
    "새로울",
    "다 아는",
    "원래",
    "그 맛",
    "익숙",  # 식상·무관심
]


def _count_by(values: list[str | None]) -> dict[str, int]:
    """None 제외하고 값별 카운트(삽입 순서 유지)."""
    c = Counter(v for v in values if v is not None)
    return dict(c)


def _analyze_message(
    passed: list[PersonaReaction], ad_analysis: AdInterpretation | None
) -> MessageReception | None:
    """메시지 수신 갭 — 의도 메시지 대비 저항 표현(과장·식상) 비율. ad_analysis 없으면 None."""
    if ad_analysis is None:
        return None
    n = len(passed)
    terms: Counter[str] = Counter()
    quotes: list[str] = []
    resisted = 0
    for r in passed:
        text = f"{r.utterance or ''} {r.perceived_message or ''}"
        hits = [t for t in _RESISTANCE_TERMS if t in text]
        if hits:
            resisted += 1
            terms.update(hits)
            if r.utterance:
                quotes.append(r.utterance[:120])
    return MessageReception(
        intended=ad_analysis.detected_message,
        resistance_rate=round(resisted / n, 4) if n else 0.0,
        resistance_terms=dict(terms.most_common(8)),
        resisted_quotes=quotes[:5],
    )


def analyze_reactions(
    reactions: list[PersonaReaction], ad_analysis: AdInterpretation | None = None
) -> ReactionAnalysis:
    """반응 리스트를 구조 분석해 ReactionAnalysis 산출. ad_analysis 있으면 메시지 수신 갭 포함."""
    passed = [r for r in reactions if r.qa_passed]
    n = len(passed)

    # ── 퍼널: 단계별 flag 합산(AISAS 비단조 데이터 대비 — 누적 통과 가정 안 함) ──
    stage_counts = {s: sum(1 for r in passed if getattr(r.aisas, s)) for s in AISAS_STAGES}
    funnel = [
        FunnelStage(
            stage=s,
            passed=stage_counts[s],
            pass_rate=round(stage_counts[s] / n, 4) if n else 0.0,
        )
        for s in AISAS_STAGES
    ]

    # ── 병목: 인접 단계 인원 감소 최대 구간(동률이면 앞 단계 우선) ──
    bottleneck: Bottleneck | None = None
    best_drop = 0
    for prev, cur in zip(AISAS_STAGES, AISAS_STAGES[1:], strict=False):
        dropped = stage_counts[prev] - stage_counts[cur]
        if dropped > best_drop:
            best_drop = dropped
            bottleneck = Bottleneck(
                from_stage=prev,
                to_stage=cur,
                dropped=dropped,
                drop_rate=round(dropped / stage_counts[prev], 4) if stage_counts[prev] else 0.0,
            )

    # ── 이탈·거부·감정 분해 ──
    by_drop_stage = _count_by([r.drop_stage for r in passed])
    by_drop_reason = _count_by(
        [str(r.drop_reason_tag) if r.drop_reason_tag else None for r in passed]
    )
    emotion_dist = _count_by([str(r.emotion_tag) for r in passed])

    rejected = [r for r in passed if r.rejected]
    rejection = RejectionBreakdown(
        rejected_count=len(rejected),
        rejection_rate=round(len(rejected) / n, 4) if n else 0.0,
        by_rejection_reason_tag=_count_by(
            [str(r.rejection_reason_tag) if r.rejection_reason_tag else None for r in rejected]
        ),
        distrust_count=sum(1 for r in passed if str(r.emotion_tag) == "distrust"),
    )

    # ── 소비자 그룹(선발 후보 풀, 겹침 허용) ──
    groups = GroupMembers(
        finishers=[r.persona_id for r in passed if r.aisas.action],
        undecided=[r.persona_id for r in passed if r.aisas.interest and not r.aisas.action],
        rejectors=[r.persona_id for r in passed if r.rejected],
        distrusters=[r.persona_id for r in passed if str(r.emotion_tag) == "distrust"],
        early_drop=[r.persona_id for r in passed if r.drop_stage == "interest"],
    )

    return ReactionAnalysis(
        total_n=n,
        funnel=funnel,
        bottleneck=bottleneck,
        by_drop_stage=by_drop_stage,
        by_drop_reason_tag=by_drop_reason,
        emotion_dist=emotion_dist,
        rejection=rejection,
        groups=groups,
        message=_analyze_message(passed, ad_analysis),
    )
