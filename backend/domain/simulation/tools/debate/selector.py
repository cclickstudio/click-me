# 조각 10-a — 토론 패널 구성(결정론, LLM✗). 전문가 4명 합성 + 일반인 2명 선발.
#
# 전문가 4(도메인2·마케팅2)는 카테고리(ad_analysis)로 합성, 일반인 2(피벗·비판자)는 반응자에서 선발.
# 규칙은 절대값을 박지 않는다 — 일반인은 "조건 필터 → 정렬 → 타이브레이크"의 상대적 선택.
# 상세 규칙: docs/simulation/debate/persona-debate-pipeline.md ②③
from __future__ import annotations

from statistics import median

from domain.simulation.contracts.debate_schemas import SelectedPanel, SelectedParticipant
from domain.simulation.contracts.schemas import AdInterpretation, PersonaReaction

# 전문가 4명 고정 스펙 — (persona_id, slot, role, 프로필 템플릿). 도메인 2는 {category} 슬롯 주입.
EXPERT_SPECS: list[tuple[str, int, str, str]] = [
    (
        "EXPERT-domain-product",
        1,
        "도메인 전문가(제품·카테고리)",
        "{category} 분야 제품·카테고리 전문가",
    ),
    (
        "EXPERT-domain-market",
        2,
        "도메인 전문가(시장·유통)",
        "{category} 분야 시장·유통·경쟁 전문가",
    ),
    ("EXPERT-mkt-performance", 3, "마케팅 전문가(퍼포먼스)", "퍼포먼스·그로스 마케터"),
    ("EXPERT-mkt-brand", 4, "마케팅 전문가(브랜드)", "브랜드·크리에이티브 전문가"),
]
PIVOT_SLOT, CRITIC_SLOT = 5, 6  # 일반인 2슬롯


def is_undecided(r: PersonaReaction) -> bool:
    """미전환: 흥미는 있으나 행동 안 함."""
    return r.aisas.interest and not r.aisas.action


def stance_score(r: PersonaReaction) -> float:
    """입장 점수(비판자 선정 전용) — AISAS 단계 + 구매의도/신뢰 + 거부. 이를수록 부정.

    drop_stage는 LLM 출력이라 attention 등도 올 수 있어 .get으로 KeyError 방어(미정의=중립 1).
    """
    stage_rank = {"attention": 0, "interest": 0, "search": 1, "action": 2, "share": 2, None: 3}
    s = float(stage_rank.get(r.drop_stage, 1))
    s += (r.purchase_intent - 3) + (r.trust - 3) * 0.5
    if r.rejected:
        s -= 5
    return s


def detect_category(ad_analysis: AdInterpretation | None) -> str:
    """광고 카테고리를 결정론 추출 — 도메인 전문가 프로필 슬롯에 주입. 없으면 generic."""
    if ad_analysis is None:
        return "해당 제품"
    detail = ad_analysis.mismatch_detail or {}
    cat = detail.get("category") if isinstance(detail, dict) else None
    declared = cat.get("declared") if isinstance(cat, dict) else None
    return declared or ad_analysis.detected_industry or "해당 제품"


def pick_representative(group: list[PersonaReaction]) -> PersonaReaction | None:
    """그룹의 '전형'(중앙값 근접) 1명 — 특이한 사람이 아니라 가장 전형적인 사람. 동점은 id순."""
    if not group:
        return None
    pi_med = median(p.purchase_intent for p in group)
    tr_med = median(p.trust for p in group)
    return min(
        group,
        key=lambda p: (abs(p.purchase_intent - pi_med) + abs(p.trust - tr_med), p.persona_id),
    )


def pick_pivot(pool: list[PersonaReaction]) -> PersonaReaction | None:
    """피벗 = 신뢰-행동 갭 최대. 미전환자 중 ① 신뢰 최고 → ② 갭(trust−pi) 최대 → ③ id순."""
    cands = [p for p in pool if is_undecided(p)]
    if not cands:
        return None
    tmax = max(p.trust for p in cands)
    top = [p for p in cands if p.trust == tmax]
    gmax = max(p.trust - p.purchase_intent for p in top)
    final = [p for p in top if p.trust - p.purchase_intent == gmax]
    return min(final, key=lambda p: p.persona_id)


def pick_critic(pool: list[PersonaReaction], exclude_id: str | None) -> PersonaReaction | None:
    """비판자 = 가장 부정적인 1명(거부·불신이 자동 하위). 피벗 제외 → 항상 다른 사람."""
    cands = [p for p in pool if p.persona_id != exclude_id]
    if not cands:
        return None
    return min(cands, key=lambda r: (stance_score(r), r.persona_id))


def _expert_participants(category: str) -> list[SelectedParticipant]:
    """전문가 4명 합성 — 도메인 2는 카테고리 주입, 마케팅 2는 고정. 반응 없음(분석결과 grounded)."""
    return [
        SelectedParticipant(
            persona_id=pid,
            slot=slot,
            role=role,
            stance_score=0.0,
            is_expert=True,
            persona_profile=tmpl.format(category=category),
        )
        for pid, slot, role, tmpl in EXPERT_SPECS
    ]


def select_panel(
    reactions: list[PersonaReaction], ad_analysis: AdInterpretation | None = None
) -> SelectedPanel:
    """패널 구성 — 전문가 4명(합성) + 일반인 2명(피벗·비판자, 실제 반응자에서 선발)."""
    pool = [r for r in reactions if r.qa_passed]
    participants: list[SelectedParticipant] = _expert_participants(detect_category(ad_analysis))

    # 일반인 슬롯5 피벗 — 미전환자 없으면 전형으로 보충.
    pivot = pick_pivot(pool)
    fallback_pivot = pivot is None
    if pivot is None:
        pivot = pick_representative(pool)
    pivot_id = pivot.persona_id if pivot is not None else None
    if pivot is not None:
        participants.append(
            SelectedParticipant(
                persona_id=pivot.persona_id,
                slot=PIVOT_SLOT,
                role="피벗",
                stance_score=round(stance_score(pivot), 3),
                is_fallback=fallback_pivot,
            )
        )

    # 일반인 슬롯6 비판자 — 피벗 제외, 가장 부정적인 1명(항상 1명 확보).
    critic = pick_critic(pool, pivot_id)
    critic_secured = False
    if critic is not None:
        participants.append(
            SelectedParticipant(
                persona_id=critic.persona_id,
                slot=CRITIC_SLOT,
                role="비판자",
                stance_score=round(stance_score(critic), 3),
            )
        )
        critic_secured = stance_score(critic) < 0  # 실제 부정 입장일 때만(좋은 광고면 False)

    parts = sorted(participants, key=lambda c: c.slot)
    return SelectedPanel(participants=parts, pivot_id=pivot_id, critic_secured=critic_secured)
