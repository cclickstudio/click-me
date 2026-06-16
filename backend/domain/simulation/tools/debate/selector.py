# 조각 10-a — 토론 패널 선발(결정론, LLM✗). 실제 반응자 전원 중 규칙으로 6명을 고른다.
#
# 규칙은 절대값을 박지 않는다 — 전부 "조건 필터 → 정렬 → 타이브레이크"의 상대적 선택이라
# 데이터가 바뀌면 그 안에서 다시 계산된다. 배타 배정(한 사람 1슬롯), 빈 슬롯은 다음 우선순위로 보충.
# 상세 규칙: docs/simulation/debate/persona-debate-pipeline.md ②③
from __future__ import annotations

from statistics import median

from domain.simulation.contracts.debate_schemas import SelectedPanel, SelectedParticipant
from domain.simulation.contracts.schemas import PersonaReaction

# 6개 고정 슬롯 — 희소 신호(거부·불신) 먼저, 흔한 무리는 나중. 위에서부터 배타 배정.
SLOT_ROLES: dict[int, str] = {
    1: "완주자",
    2: "피벗",
    3: "거부자",
    4: "불신자",
    5: "초기이탈",
    6: "미온다수2",
}


def is_undecided(r: PersonaReaction) -> bool:
    """미전환: 흥미는 있으나 행동 안 함."""
    return r.aisas.interest and not r.aisas.action


def stance_score(r: PersonaReaction) -> float:
    """입장 점수(③ 모델 배정 전용) — AISAS 단계 + 구매의도/신뢰 + 거부. 이를수록 부정.

    drop_stage는 LLM 출력이라 attention 등도 올 수 있어 .get으로 KeyError 방어(미정의=중립 1).
    """
    stage_rank = {"attention": 0, "interest": 0, "search": 1, "action": 2, "share": 2, None: 3}
    s = float(stage_rank.get(r.drop_stage, 1))
    s += (r.purchase_intent - 3) + (r.trust - 3) * 0.5
    if r.rejected:
        s -= 5
    return s


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


def pick_second_undecided(
    pool: list[PersonaReaction], pivot: PersonaReaction
) -> PersonaReaction | None:
    """미온2 = 피벗과 신뢰가 가장 다른 미전환자(같은 무리의 다른 결). 동점은 전형→id순."""
    cands = [p for p in pool if is_undecided(p)]
    if not cands:
        return None
    dmax = max(abs(p.trust - pivot.trust) for p in cands)
    top = [p for p in cands if abs(p.trust - pivot.trust) == dmax]
    return pick_representative(top)


def select_panel(reactions: list[PersonaReaction], panel_size: int = 6) -> SelectedPanel:
    """반응자 전원에서 패널 선발 — 6슬롯 배타 배정 + 빈 슬롯 보충 + 비판자 1명 확보."""
    pool = [r for r in reactions if r.qa_passed]
    chosen: dict[str, SelectedParticipant] = {}

    def remaining() -> list[PersonaReaction]:
        return [r for r in pool if r.persona_id not in chosen]

    def take(r: PersonaReaction, slot: int, fallback: bool = False) -> PersonaReaction:
        chosen[r.persona_id] = SelectedParticipant(
            persona_id=r.persona_id,
            slot=slot,
            role=SLOT_ROLES[slot],
            stance_score=round(stance_score(r), 3),
            is_fallback=fallback,
        )
        return r

    def fill(slot: int, cands: list[PersonaReaction]) -> PersonaReaction | None:
        """슬롯 후보가 있으면 전형을 뽑고, 없으면 remaining 전체에서 보충(is_fallback)."""
        pick = pick_representative(cands)
        if pick is not None:
            return take(pick, slot)
        rem = remaining()
        pick = pick_representative(rem)
        return take(pick, slot, fallback=True) if pick is not None else None

    # 슬롯1 완주자
    fill(1, [r for r in remaining() if r.aisas.action])

    # 슬롯2 피벗 — 신뢰-행동 갭. 미전환자 없으면 보충.
    pivot = pick_pivot(remaining())
    if pivot is not None:
        take(pivot, 2)
    else:
        pivot = fill(2, [])

    # 슬롯3 거부자 / 슬롯4 불신자 / 슬롯5 초기이탈 (희소 신호 우선)
    fill(3, [r for r in remaining() if r.rejected])
    fill(4, [r for r in remaining() if str(r.emotion_tag) == "distrust"])
    fill(5, [r for r in remaining() if r.drop_stage == "interest"])

    # 슬롯6 미온2 — 피벗과 신뢰 차 최대. 피벗·미전환자 없으면 보충.
    slot6 = pick_second_undecided(remaining(), pivot) if pivot is not None else None
    if slot6 is not None:
        take(slot6, 6)
    else:
        fill(6, [])

    # panel_size가 6 미만이면 슬롯 순서대로 잘라낸다(현재 기본 6).
    parts = sorted(chosen.values(), key=lambda c: c.slot)[:panel_size]

    # 비판자 확보 — 패널에 부정 입장(stance<0)이 0명이면 remaining 중 가장 부정적인 1명으로
    # 마지막 슬롯을 교체(칭찬 일색 메아리방 방지). 교체 대상이 더 부정적일 때만.
    critic_secured = any(c.stance_score < 0 for c in parts)
    if not critic_secured and parts:
        rem = remaining()
        if rem:
            worst = min(rem, key=lambda r: (stance_score(r), r.persona_id))
            replaced = parts[-1]
            if stance_score(worst) < replaced.stance_score:
                del chosen[replaced.persona_id]
                take(worst, replaced.slot, fallback=True)
                parts = sorted(chosen.values(), key=lambda c: c.slot)[:panel_size]
                critic_secured = any(c.stance_score < 0 for c in parts)

    pivot_id = next((c.persona_id for c in parts if c.slot == 2), None)
    return SelectedPanel(participants=parts, pivot_id=pivot_id, critic_secured=critic_secured)
