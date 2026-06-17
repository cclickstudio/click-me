# 조각 10-a — 토론 패널 구성(결정론, LLM✗). 전문가 4명 합성 + 일반인 lay_count(2/4)명 선발.
#
# 전문가 4(도메인2·마케팅2)는 카테고리(ad_analysis)로 합성, 일반인은 반응자에서 선발.
# 규칙은 절대값을 박지 않는다 — 일반인은 "조건 필터 → 정렬 → 타이브레이크"의 상대적 선택.
# 상세 규칙: docs/simulation/debate/persona-debate-pipeline.md ②③
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from statistics import median, pstdev

from domain.simulation.contracts.debate_schemas import SelectedPanel, SelectedParticipant
from domain.simulation.contracts.schemas import AdInterpretation, Persona, PersonaReaction

# LLM 재랭킹 게이트 콜러블 — (역할, 역할정의, 동점 후보) → 고른 persona_id. None이면 100% 결정론.
# 스칼라(trust·purchase_intent 등)로 못 가른 '동점 최상위군'이 2명 이상일 때만 호출된다.
RerankFn = Callable[[str, str, list[PersonaReaction]], str]

# 역할 정의 — 동점 시 LLM이 텍스트(utterance·사유)로 판단할 기준. 결정론 타이브레이크가 못 보는 결.
ROLE_DEFS: dict[str, str] = {
    "피벗": (
        "신뢰는 하지만 아직 행동(클릭·구매)하지 않은 사람 중, 조금만 설득하면 넘어올 '스윙보터'. "
        "이미 마음을 닫았거나 카테고리 자체에 관심이 없는 사람은 피벗이 아니다."
    ),
    "비판자": (
        "밀어도 안 움직이는 구조적 안티 — 제품·브랜드 전반에 대한 불신처럼 "
        "광고를 고쳐도 풀리지 않는 '개선의 천장'. "
        "단지 이 광고가 식상하거나 노출이 잦아 피곤한 사람과 구분하라(그건 광고만 고치면 풀린다)."
    ),
    "완주자": "끝까지 간 긍정 극의 전형 — 가장 대표적으로 만족하고 행동까지 간 소비자.",
    "미온": "관심은 있으나 굳이 움직이지 않은 다수의 결 — 피벗과는 다른 방식으로 미지근한 사람.",
}

# 타깃 적합 — 반응 분포로 타깃층(관심 보인 인구) 역산 후, 타깃 밖 후보를 일반인 풀에서 배제.
TARGET_AGE_TOL = 12  # 타깃 나이 중심에서 이 이내면 적합(강: 성별도 일치해야)
TARGET_GENDER_MIN = 0.35  # 관심층에서 이 비율 이상인 성별을 타깃 성별로 인정
# 성별 역산 최소 표본 — 관심층이 이 미만이면 성별 쏠림을 신뢰 안 함(성별로 안 좁히고 나이로만).
# 스마트폰처럼 성중립 제품이 작은 표본에서 우연히 한 성별로 쏠려도 배제되지 않게 한다.
GENDER_MIN_SAMPLE = 8

# 전 연령형(타깃 불명확) 판정 — 관심층 나이 분산이 크거나 detected_target이 포괄어면 배제를 끈다.
# 라면처럼 전 연령 소비 제품은 중앙값으로 좁히면 양 끝(10대·고령)을 잘못 배제하기 때문.
BROAD_TARGET_AGE_STD = 9.5  # 관심층 나이 std 이 이상 → 전 연령형(좁은 타깃은 보통 7~8)
_BROAD_TARGET_TERMS = [
    "일반 대중",
    "일반 소비자",
    "전 연령",
    "전반",
    "누구나",
    "남녀노소",
    "온 가족",
    "전 국민",
    "모든",
]

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
# 일반인 slot 시작(1~4는 전문가). 선발 우선순위 순으로 5,6,7,…에 연속 배정(엔진 균등 유지).
LAY_SLOT_START = 5
LAY_COUNTS = (2, 4)  # 지원하는 일반인 수 — 2(피벗·비판자) / 4(+완주자·미온)


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


def _is_broad_target(
    pool: list[PersonaReaction],
    by_id: dict[str, Persona],
    ad_analysis: AdInterpretation | None,
) -> bool:
    """전 연령형(타깃 불명확) 판정 — detected_target 포괄어 OR 관심층 나이 분산이 큼.

    좁은 타깃(예: 프리미엄 가전 30·40대)은 중앙값으로 좁혀 배제하지만, 라면처럼
    전 연령 소비 제품은 좁히면 양 끝을 잘못 잘라낸다 → 배제 끄고 연령 다양성 선발.
    """
    target = (ad_analysis.detected_target or "") if ad_analysis else ""
    if any(t in target for t in _BROAD_TARGET_TERMS):
        return True
    ages = [
        by_id[r.persona_id].age
        for r in pool
        if r.aisas.interest and not r.rejected and r.persona_id in by_id
    ]
    return len(ages) > 1 and pstdev(ages) >= BROAD_TARGET_AGE_STD


def _final_pick(
    group: list[PersonaReaction],
    chosen_ages: list[int],
    by_id: dict[str, Persona],
    age_spread: bool,
) -> PersonaReaction | None:
    """동점 그룹에서 최종 1명 — 연령 다양성 ON이면 '기선발자와 나이 차 최대 → id순', OFF면 id순.

    핵심 기준(stance·갭·전형)은 호출부가 이미 적용했고, 여기선 남은 동점만 가른다.
    """
    if not group:
        return None
    if not age_spread:
        return min(group, key=lambda r: r.persona_id)

    def spread(r: PersonaReaction) -> int:
        p = by_id.get(r.persona_id)
        if p is None or not chosen_ages:
            return 0
        return min(abs(p.age - a) for a in chosen_ages)  # 가장 가까운 기선발자와의 거리

    return min(group, key=lambda r: (-spread(r), r.persona_id))  # 거리 최대 → id순


def _pick_or_rerank(
    role: str,
    tie: list[PersonaReaction],
    chosen_ages: list[int],
    by_id: dict[str, Persona],
    age_spread: bool,
    rerank_fn: RerankFn | None,
) -> PersonaReaction | None:
    """동점 최상위군 tie에서 1명 — rerank_fn 있고 2명+면 LLM(텍스트), 아니면 결정론(_final_pick).

    스칼라가 이미 못 가른 동점에서만 LLM을 부른다(=margin 게이트). 1명이면 LLM 불필요,
    LLM 실패·무효 응답이면 결정론으로 안전 폴백 → 게이트가 정확도를 떨어뜨릴 일이 없다.
    """
    if not tie:
        return None
    if rerank_fn is None or len(tie) < 2:
        return _final_pick(tie, chosen_ages, by_id, age_spread)
    try:
        pid = rerank_fn(role, ROLE_DEFS.get(role, role), tie)
    except Exception:
        return _final_pick(tie, chosen_ages, by_id, age_spread)
    chosen = next((r for r in tie if r.persona_id == pid), None)
    return chosen if chosen is not None else _final_pick(tie, chosen_ages, by_id, age_spread)


def pick_representative(
    group: list[PersonaReaction],
    chosen_ages: list[int] | None = None,
    by_id: dict[str, Persona] | None = None,
    age_spread: bool = False,
    role: str = "전형",
    rerank_fn: RerankFn | None = None,
) -> PersonaReaction | None:
    """그룹의 '전형'(중앙값 근접) 1명 — 동점은 LLM(rerank_fn) → 연령 다양성 → id순."""
    if not group:
        return None
    pi_med = median(p.purchase_intent for p in group)
    tr_med = median(p.trust for p in group)
    dmin = min(abs(p.purchase_intent - pi_med) + abs(p.trust - tr_med) for p in group)
    tie = [p for p in group if abs(p.purchase_intent - pi_med) + abs(p.trust - tr_med) == dmin]
    return _pick_or_rerank(role, tie, chosen_ages or [], by_id or {}, age_spread, rerank_fn)


def pick_pivot(
    pool: list[PersonaReaction],
    chosen_ages: list[int] | None = None,
    by_id: dict[str, Persona] | None = None,
    age_spread: bool = False,
    rerank_fn: RerankFn | None = None,
) -> PersonaReaction | None:
    """피벗 = 신뢰-행동 갭 최대. 미전환자 중 ① 신뢰 최고 → ② 갭(trust−pi) 최대 → ③ 동점타이."""
    cands = [p for p in pool if is_undecided(p)]
    if not cands:
        return None
    tmax = max(p.trust for p in cands)
    top = [p for p in cands if p.trust == tmax]
    gmax = max(p.trust - p.purchase_intent for p in top)
    final = [p for p in top if p.trust - p.purchase_intent == gmax]
    return _pick_or_rerank("피벗", final, chosen_ages or [], by_id or {}, age_spread, rerank_fn)


def pick_critic(
    pool: list[PersonaReaction],
    exclude_id: str | None,
    chosen_ages: list[int] | None = None,
    by_id: dict[str, Persona] | None = None,
    age_spread: bool = False,
    rerank_fn: RerankFn | None = None,
) -> PersonaReaction | None:
    """비판자 = 가장 부정적인 1명(거부·불신이 자동 하위). 피벗 제외 → 항상 다른 사람."""
    cands = [p for p in pool if p.persona_id != exclude_id]
    if not cands:
        return None
    smin = min(stance_score(r) for r in cands)
    tie = [r for r in cands if stance_score(r) == smin]
    return _pick_or_rerank("비판자", tie, chosen_ages or [], by_id or {}, age_spread, rerank_fn)


def pick_finisher(
    pool: list[PersonaReaction],
    chosen_ages: list[int] | None = None,
    by_id: dict[str, Persona] | None = None,
    age_spread: bool = False,
    rerank_fn: RerankFn | None = None,
) -> PersonaReaction | None:
    """완주자 = action 전형(끝까지 간 긍정 극). 클릭 0% 광고면 가장 긍정적인 1명으로 보충."""
    fin = [p for p in pool if p.aisas.action]
    if fin:
        return pick_representative(fin, chosen_ages, by_id, age_spread, "완주자", rerank_fn)
    if not pool:
        return None
    smax = max(stance_score(r) for r in pool)  # 가장 덜 부정(긍정 천장)
    tie = [r for r in pool if stance_score(r) == smax]
    return _pick_or_rerank("완주자", tie, chosen_ages or [], by_id or {}, age_spread, rerank_fn)


def pick_second_undecided(
    pool: list[PersonaReaction],
    pivot: PersonaReaction | None,
    chosen_ages: list[int] | None = None,
    by_id: dict[str, Persona] | None = None,
    age_spread: bool = False,
    rerank_fn: RerankFn | None = None,
) -> PersonaReaction | None:
    """미온2 = 미전환자 중 피벗과 신뢰가 가장 다른 1명(같은 무리의 다른 결). 동점은 전형→타이."""
    cands = [p for p in pool if is_undecided(p)]
    if not cands or pivot is None:
        return None
    dmax = max(abs(p.trust - pivot.trust) for p in cands)
    top = [p for p in cands if abs(p.trust - pivot.trust) == dmax]
    return pick_representative(top, chosen_ages, by_id, age_spread, "미온", rerank_fn)


def _target_profile(
    pool: list[PersonaReaction], by_id: dict[str, Persona]
) -> tuple[float, set[str]] | None:
    """타깃층 역산 — 관심 보인(interest·비거부) 인구의 나이 중심 + 다수 성별. 없으면 전체로.

    detected_target이 '일반 대중'처럼 무의미할 때, 실제 반응으로 진짜 관심층을 잡는다.
    """
    engaged = [
        by_id[r.persona_id]
        for r in pool
        if r.aisas.interest and not r.rejected and r.persona_id in by_id
    ]
    base = engaged or [by_id[r.persona_id] for r in pool if r.persona_id in by_id]
    if not base:
        return None
    age_center = float(median(p.age for p in base))
    gc = Counter(p.gender for p in base)
    total = sum(gc.values())
    if total < GENDER_MIN_SAMPLE:
        # 표본 부족 — 성별 쏠림이 우연일 수 있어 신뢰 안 함. 전체 성별 허용(성별로 안 좁힘).
        genders = {p.gender for p in by_id.values()}
    else:
        genders = {g for g, c in gc.items() if c / total >= TARGET_GENDER_MIN} or set(gc)
    return age_center, genders


def _filter_on_target(
    pool: list[PersonaReaction], personas: list[Persona], need: int
) -> tuple[list[PersonaReaction], float | None, list[str], int]:
    """타깃 밖 후보 배제(강: 나이·성별 둘 다 맞아야). 남은 풀 < need면 허용범위 단계 완화.

    인구통계 없는 반응(by_id에 없음)은 배제하지 않는다(정보 부재 ≠ 타깃 밖).
    """
    by_id = {p.persona_id: p for p in personas}
    prof = _target_profile(pool, by_id)
    if prof is None:
        return pool, None, [], 0
    age_c, genders = prof

    def on_target(r: PersonaReaction, tol: float) -> bool:
        p = by_id.get(r.persona_id)
        if p is None:
            return True
        return abs(p.age - age_c) <= tol and p.gender in genders

    for tol in (TARGET_AGE_TOL, TARGET_AGE_TOL + 8, TARGET_AGE_TOL + 16, 200.0):
        kept = [r for r in pool if on_target(r, tol)]
        if len(kept) >= need:
            return kept, age_c, sorted(genders), len(pool) - len(kept)
    return pool, age_c, sorted(genders), 0


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
    reactions: list[PersonaReaction],
    ad_analysis: AdInterpretation | None = None,
    lay_count: int = 4,
    personas: list[Persona] | None = None,
    rerank_fn: RerankFn | None = None,
) -> SelectedPanel:
    """패널 구성 — 전문가 4명(합성) + 일반인 lay_count명(실제 반응자에서 선발).

    lay_count=2: 피벗·비판자(두 극) / lay_count=4: +완주자·미온(분포 범위 커버).
    personas 주입 시 타깃 적합 선발 — 타깃 밖(엉뚱한 인구) 후보를 일반인 풀에서 배제.
    일반인은 선발 우선순위(피벗→비판자→완주자→미온) 순으로 slot 5,6,…에 연속 배정.
    rerank_fn 주입 시: 스칼라로 못 가른 '동점 후보'만 LLM이 텍스트로 재판단(margin 게이트).
    None이면 100% 결정론(현행 동작 보존).
    """
    if lay_count not in LAY_COUNTS:
        raise ValueError(f"lay_count는 {LAY_COUNTS} 중 하나여야 합니다: {lay_count}")
    pool = [r for r in reactions if r.qa_passed]

    # 타깃 적합 — personas 있을 때만. 전 연령형이면 배제를 끄고 연령 다양성 선발(age_spread)로.
    by_id: dict[str, Persona] = {p.persona_id: p for p in personas} if personas else {}
    target_age: float | None = None
    target_genders: list[str] = []
    excluded = 0
    broad = False
    age_spread = False
    if personas:
        broad = _is_broad_target(pool, by_id, ad_analysis)
        if broad:
            age_spread = True  # 전 연령형 → 배제 안 함, 일반인 4명을 연령적으로 퍼뜨려 뽑음
        else:
            pool, target_age, target_genders, excluded = _filter_on_target(
                pool, personas, lay_count
            )

    participants: list[SelectedParticipant] = _expert_participants(detect_category(ad_analysis))
    chosen: set[str] = set()
    chosen_ages: list[int] = []  # 연령 다양성 타이브레이크용(선발 진행하며 누적)
    lay: list[tuple[PersonaReaction, str, bool]] = []  # (반응자, 역할, fallback) 선발 순

    def remaining() -> list[PersonaReaction]:
        return [r for r in pool if r.persona_id not in chosen]

    def add(r: PersonaReaction | None, role: str, fb: bool = False) -> None:
        if r is not None:
            chosen.add(r.persona_id)
            lay.append((r, role, fb))
            p = by_id.get(r.persona_id)
            if p is not None:
                chosen_ages.append(p.age)

    # 피벗 — 미전환 중 신뢰-행동 갭. 없으면 전형으로 보충. (우선순위 1, 연령 기선이라 spread 무효)
    pivot = pick_pivot(pool, chosen_ages, by_id, age_spread, rerank_fn)
    fallback_pivot = pivot is None
    if pivot is None:
        pivot = pick_representative(pool, chosen_ages, by_id, age_spread, "피벗", rerank_fn)
    pivot_id = pivot.persona_id if pivot is not None else None
    add(pivot, "피벗", fallback_pivot)

    # 비판자 — 가장 부정적인 1명(부정 극 먼저 확보, 피벗 제외). (우선순위 2)
    critic = pick_critic(remaining(), pivot_id, chosen_ages, by_id, age_spread, rerank_fn)
    critic_secured = critic is not None and stance_score(critic) < 0
    add(critic, "비판자")

    if lay_count >= 4:
        # 완주자 — action 전형(긍정 극). 클릭 0%면 가장 긍정적인 1명. (우선순위 3)
        add(pick_finisher(remaining(), chosen_ages, by_id, age_spread, rerank_fn), "완주자")
        # 미온 — 미전환 중 피벗과 결 다른 1명. 미전환 소진이면 전형으로 보충. (우선순위 4)
        second = pick_second_undecided(
            remaining(), pivot, chosen_ages, by_id, age_spread, rerank_fn
        )
        if second is not None:
            add(second, "미온")
        else:
            add(
                pick_representative(remaining(), chosen_ages, by_id, age_spread, "미온", rerank_fn),
                "미온",
                fb=True,
            )

    # 선발 순서대로 slot 5,6,… 연속 부여(빈 slot 없음 → 엔진 라운드로빈 균등).
    for i, (r, role, fb) in enumerate(lay):
        participants.append(
            SelectedParticipant(
                persona_id=r.persona_id,
                slot=LAY_SLOT_START + i,
                role=role,
                stance_score=round(stance_score(r), 3),
                is_fallback=fb,
            )
        )

    parts = sorted(participants, key=lambda c: c.slot)
    return SelectedPanel(
        participants=parts,
        pivot_id=pivot_id,
        critic_secured=critic_secured,
        target_age_center=target_age,
        target_genders=target_genders,
        excluded_off_target=excluded,
        broad_target=broad,
    )
