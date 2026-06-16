# 조각 10-b — 엔진·이름 배정(결정론, LLM✗). 선발 6명에 모델·페르소나명을 부여한다.
#
# 엔진은 입장순 교차 배정(엔진 ⊥ 입장) — 한 엔진이 한쪽에 쏠리지 않게. 피벗은 Haiku, Judge=Opus.
# 이름은 persona_id 기반 결정론(같은 id → 항상 같은 이름). 운영은 factory 이름을 우선 승계.
# 상세 규칙: docs/simulation/debate/persona-debate-pipeline.md ③⑤
from __future__ import annotations

import hashlib

from domain.simulation.contracts.debate_schemas import (
    AssignedPanel,
    DebateParticipant,
    SelectedPanel,
)

JUDGE_ENGINE = "opus"  # Opus 4.8 (종합·최종 액션, 호출 적음 → 강모델). 별도 고정.
PIVOT_ENGINE = "haiku"  # Haiku 4.5 (가장 중요한 질문, 연기엔 충분). 피벗에 고정.
# 피벗 제외 나머지에 채울 엔진 — 토론자 총 Haiku 2(피벗 포함)/GPT 2/Gemini 2. 입장 순서로 채운다.
REST_QUOTA = ["gpt", "gemini", "haiku", "gpt", "gemini"]

# 이름 풀(결정론 부여) — 더미엔 인구정보가 없어 persona_id 해시로 고른다.
# 성별을 먼저 정하고 성별에 맞는 이름 풀에서 골라 '남성+여성이름' 같은 불일치를 막는다.
_SURNAMES = [
    "김", "이", "박", "최", "정", "강", "조", "윤", "장", "임",
    "한", "오", "서", "신", "권", "황", "안", "송", "배", "홍",
]
_MALE_GIVEN = [
    "민준", "도윤", "예준", "지호", "준서", "현우", "건우", "우진", "선우", "정우",
    "승현", "시우", "주원", "준우", "민재", "지훈", "성민", "태현", "동현", "재현",
]
_FEMALE_GIVEN = [
    "서연", "하은", "수아", "지유", "다은", "은서", "채원", "소율", "예린", "윤서",
    "하린", "서윤", "수빈", "예은", "가은", "유나", "서아", "민서", "지원", "혜원",
]

# 역할 → 성향 라벨(프로필 끝에 붙임). 운영은 factory 프로필로 교체.
_ROLE_TRAIT = {
    "완주자": "적극형",
    "피벗": "신뢰형",
    "거부자": "비판형",
    "불신자": "불신형",
    "초기이탈": "무관심형",
    "미온다수2": "미온형",
}

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


def assign_panel(panel: SelectedPanel) -> AssignedPanel:
    """선발 패널에 엔진·이름·프로필을 결정론 부여."""
    selected = panel.participants
    pivot_id = panel.pivot_id

    # 엔진 배정 — 피벗 제외 나머지를 입장(stance)순 정렬 후 REST_QUOTA 순서로(엔진 ⊥ 입장).
    rest = sorted(
        (p for p in selected if p.persona_id != pivot_id),
        key=lambda p: (p.stance_score, p.persona_id),
    )
    engine_of: dict[str, str] = {}
    if pivot_id is not None:
        engine_of[pivot_id] = PIVOT_ENGINE
    for i, p in enumerate(rest):
        engine_of[p.persona_id] = REST_QUOTA[i % len(REST_QUOTA)]

    # 이름 부여 — slot 순(결정론)으로 처리해 중복 회피가 재현되게 한다.
    taken: set[str] = set()
    participants: list[DebateParticipant] = []
    for p in sorted(selected, key=lambda c: c.slot):
        gender = _gender_for(p.persona_id)  # 이름·프로필이 같은 성별을 공유
        name = _name_for(p.persona_id, gender, taken)
        taken.add(name)
        participants.append(
            DebateParticipant(
                persona_id=p.persona_id,
                slot=p.slot,
                role=p.role,
                stance_score=p.stance_score,
                is_fallback=p.is_fallback,
                engine=engine_of.get(p.persona_id, PIVOT_ENGINE),
                persona_name=name,
                persona_profile=_profile_for(p.persona_id, gender, p.role),
            )
        )

    return AssignedPanel(
        participants=participants,
        pivot_id=pivot_id,
        judge_engine=JUDGE_ENGINE,
        critic_secured=panel.critic_secured,
    )
