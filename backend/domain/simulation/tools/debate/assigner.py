# 조각 10-b — 엔진·이름 배정(결정론, LLM✗). 패널 6명에 모델·페르소나명을 부여한다.
#
# 엔진은 역할 기반 라운드로빈(엔진 ⊥ 역할) — 한 엔진이 한 역할군에 쏠리지 않게. Judge=Sonnet.
# 이름은 persona_id 기반 결정론(같은 id → 항상 같은 이름). 운영은 factory 이름을 우선 승계.
# 상세 규칙: docs/simulation/debate/persona-debate-pipeline.md ③⑤
from __future__ import annotations

import hashlib

from domain.simulation.contracts.debate_schemas import (
    AssignedPanel,
    DebateParticipant,
    SelectedPanel,
)

JUDGE_ENGINE = "sonnet"  # Sonnet 4.6 (종합·최종 액션, 호출 적음 / Opus 4.8에서 다운). 별도 고정.
# slot별 엔진 라운드로빈((slot-1)%2) — 엔진 ⊥ 역할. Gemini 제거(응답 실패 잦음) → Haiku·GPT 2엔진.
# 8명이면 Haiku4/GPT4, 6명(일반인2)이면 Haiku3/GPT3. slot 고정이라 전문가/일반에 엔진이 골고루.
PANEL_ENGINE = ["haiku", "gpt"]

# 이름 풀(결정론 부여) — 더미엔 인구정보가 없어 persona_id 해시로 고른다.
# 성별을 먼저 정하고 성별에 맞는 이름 풀에서 골라 '남성+여성이름' 같은 불일치를 막는다.
_SURNAMES = [
    "김",
    "이",
    "박",
    "최",
    "정",
    "강",
    "조",
    "윤",
    "장",
    "임",
    "한",
    "오",
    "서",
    "신",
    "권",
    "황",
    "안",
    "송",
    "배",
    "홍",
]
_MALE_GIVEN = [
    "민준",
    "도윤",
    "예준",
    "지호",
    "준서",
    "현우",
    "건우",
    "우진",
    "선우",
    "정우",
    "승현",
    "시우",
    "주원",
    "준우",
    "민재",
    "지훈",
    "성민",
    "태현",
    "동현",
    "재현",
]
_FEMALE_GIVEN = [
    "서연",
    "하은",
    "수아",
    "지유",
    "다은",
    "은서",
    "채원",
    "소율",
    "예린",
    "윤서",
    "하린",
    "서윤",
    "수빈",
    "예은",
    "가은",
    "유나",
    "서아",
    "민서",
    "지원",
    "혜원",
]

# 역할 → 성향 라벨(일반인 프로필 끝에 붙임). 운영은 factory 프로필로 교체.
# 전문가는 슬롯 프로필(카테고리 주입)을 직접 사용한다.
_ROLE_TRAIT = {
    "피벗": "신뢰형",
    "완주자": "적극형",
    "비판자": "비판형",
    "미온": "미온형",
}

# 일반인 말투 풀(전문가 제외) — 같은 모델로 통일해도 표현이 겹치지 않게 결정론·비복원 배정.
# 말투는 '어떻게 말하는가'(표현)일 뿐, 찬반 판단은 실제 반응 데이터를 따른다(_persona_system 가드).
_LAY_TONES = [
    "군더더기 없이 핵심만, 결론부터 짧게 말한다.",
    "본인 경험이나 사례를 곁들여 길게 풀어 말한다.",
    "단정하지 않고 '글쎄요, ~인 것 같아요' 식으로 조심스럽게 말한다.",
    "감탄사와 솔직한 감정 표현이 많다.",
    "이유와 조건을 조목조목 따지고 숫자를 챙긴다.",
    "심드렁하고 광고에 쉽게 안 넘어가는 말투다.",
    "가격·실용성 위주로 와닿는지 아닌지를 말한다.",
    "분위기·요즘 감성 위주로 직관적으로 말한다.",
]

# 직업 풀 — (직업, 최소나이, 최대나이). 직업에 맞는 나이대에서 골라 '60세 대학생'을 막는다.
_JOBS = [
    ("회사원", 26, 55),
    ("대학생", 20, 26),
    ("주부", 30, 60),
    ("자영업자", 30, 60),
    ("교사", 28, 60),
    ("간호사", 24, 50),
    ("개발자", 25, 45),
    ("디자이너", 25, 45),
    ("영업직", 26, 55),
    ("공무원", 26, 58),
    ("프리랜서", 28, 58),
    ("마케터", 26, 48),
]


def _gender_for(persona_id: str) -> str:
    """persona_id 결정론 성별 — 이름·프로필이 공유해 불일치를 막는다."""
    h = int(hashlib.sha256(persona_id.encode("utf-8")).hexdigest(), 16)
    return "남성" if (h // 20) % 2 == 0 else "여성"


def _name_for(persona_id: str, gender: str, taken: set[str]) -> str:
    """persona_id 결정론 이름 — 성·성별 맞는 이름 선택, 패널 내 중복은 다음 후보로 회피."""
    h = int(hashlib.sha256(persona_id.encode("utf-8")).hexdigest(), 16)
    surname = _SURNAMES[h % len(_SURNAMES)]
    pool = _MALE_GIVEN if gender == "남성" else _FEMALE_GIVEN
    gi = (h // 40) % len(pool)
    for k in range(len(pool)):
        name = surname + pool[(gi + k) % len(pool)]
        if name not in taken:
            return name
    return surname + pool[gi]


def _profile_for(persona_id: str, gender: str, role: str) -> str:
    """persona_id 결정론 프로필 — 직업·나이(직업별 범위)·성별 + 역할 성향. 더미용."""
    h = int(hashlib.sha256(persona_id.encode("utf-8")).hexdigest(), 16)
    job, lo, hi = _JOBS[(h // 4000) % len(_JOBS)]
    age = lo + (h // 400000) % (hi - lo + 1)
    trait = _ROLE_TRAIT.get(role, role)
    return f"{age}세 {gender} {job} · {trait}"


def _tones_for_lays(lay_ids: list[str]) -> dict[str, str]:
    """일반인에게만 말투를 결정론·비복원 배정 — 첫 일반인 id로 시작점, 이후 +1씩(겹침 회피)."""
    if not lay_ids:
        return {}
    offset = int(hashlib.sha256(lay_ids[0].encode("utf-8")).hexdigest(), 16) % len(_LAY_TONES)
    return {pid: _LAY_TONES[(offset + i) % len(_LAY_TONES)] for i, pid in enumerate(lay_ids)}


def assign_panel(panel: SelectedPanel) -> AssignedPanel:
    """패널에 엔진·이름·프로필을 결정론 부여 — 엔진은 slot 라운드로빈, 이름은 persona_id 해시."""
    selected = sorted(panel.participants, key=lambda c: c.slot)
    # 일반인 말투 배정(전문가 제외) — slot 순 id로 비복원. 같은 모델이어도 표현이 겹치지 않게.
    lay_tones = _tones_for_lays([p.persona_id for p in selected if not p.is_expert])

    # 이름 부여 — slot 순(결정론)으로 처리해 중복 회피가 재현되게 한다.
    taken: set[str] = set()
    participants: list[DebateParticipant] = []
    for p in selected:
        gender = _gender_for(p.persona_id)  # 이름·프로필이 같은 성별을 공유
        name = _name_for(p.persona_id, gender, taken)
        taken.add(name)
        # 전문가는 카테고리 주입 프로필을 그대로, 일반인은 나이·직업·성향으로 생성.
        profile = (
            p.persona_profile
            if p.is_expert and p.persona_profile
            else _profile_for(p.persona_id, gender, p.role)
        )
        participants.append(
            DebateParticipant(
                persona_id=p.persona_id,
                slot=p.slot,
                role=p.role,
                stance_score=p.stance_score,
                is_fallback=p.is_fallback,
                is_expert=p.is_expert,
                engine=PANEL_ENGINE[(p.slot - 1) % len(PANEL_ENGINE)],
                persona_name=name,
                persona_profile=profile,
                tone=lay_tones.get(p.persona_id, ""),
            )
        )

    return AssignedPanel(
        participants=participants,
        pivot_id=panel.pivot_id,
        judge_engine=JUDGE_ENGINE,
        critic_secured=panel.critic_secured,
    )
