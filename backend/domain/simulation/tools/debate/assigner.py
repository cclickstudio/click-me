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
    "전",
    "홍",
]
_GIVEN = [
    "민준",
    "서연",
    "도윤",
    "지우",
    "예준",
    "하은",
    "지호",
    "수아",
    "준서",
    "지유",
    "현우",
    "다은",
    "건우",
    "은서",
    "우진",
    "채원",
    "선우",
    "지민",
    "정우",
    "유진",
    "승현",
    "소율",
    "재윤",
    "예린",
    "시우",
    "윤서",
    "주원",
    "하린",
    "지안",
    "서윤",
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

# 직업 풀(결정론 부여) — 더미엔 인구정보가 없어 persona_id 해시로 고른다.
_JOBS = [
    "회사원",
    "대학생",
    "주부",
    "자영업자",
    "교사",
    "간호사",
    "개발자",
    "디자이너",
    "영업직",
    "공무원",
    "프리랜서",
    "마케터",
]


def _name_for(persona_id: str, taken: set[str]) -> str:
    """persona_id 결정론 이름 — sha256 해시로 성·이름 선택, 패널 내 중복은 다음 후보로 회피."""
    h = int(hashlib.sha256(persona_id.encode("utf-8")).hexdigest(), 16)
    surname = _SURNAMES[h % len(_SURNAMES)]
    gi = (h // len(_SURNAMES)) % len(_GIVEN)
    for k in range(len(_GIVEN)):
        name = surname + _GIVEN[(gi + k) % len(_GIVEN)]
        if name not in taken:
            return name
    return surname + _GIVEN[gi]


def _profile_for(persona_id: str, role: str) -> str:
    """persona_id 결정론 프로필 — 나이·성별·직업 + 역할 성향. 더미용(운영은 factory 프로필)."""
    h = int(hashlib.sha256(persona_id.encode("utf-8")).hexdigest(), 16)
    age = 20 + (h % 45)  # 20~64세
    gender = "남성" if (h // 45) % 2 == 0 else "여성"
    job = _JOBS[(h // 90) % len(_JOBS)]
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
        name = _name_for(p.persona_id, taken)
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
                persona_profile=_profile_for(p.persona_id, p.role),
            )
        )

    return AssignedPanel(
        participants=participants,
        pivot_id=pivot_id,
        judge_engine=JUDGE_ENGINE,
        critic_secured=panel.critic_secured,
    )
