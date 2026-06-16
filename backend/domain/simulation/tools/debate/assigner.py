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

# 역할 → 한 줄 프로필(인구정보 부재 시 역할로 대체). 운영은 factory 프로필로 교체.
_ROLE_PROFILE = {
    "완주자": "끝까지 반응한 적극형",
    "피벗": "신뢰는 있으나 행동 직전 멈춘 스윙형",
    "거부자": "광고를 거부한 비판형",
    "불신자": "메시지를 의심한 불신형",
    "초기이탈": "흥미 단계에서 이탈한 무관심형",
    "미온다수2": "관심은 있으나 움직이지 않은 미온형",
}


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
                persona_profile=_ROLE_PROFILE.get(p.role, p.role),
            )
        )

    return AssignedPanel(
        participants=participants,
        pivot_id=pivot_id,
        judge_engine=JUDGE_ENGINE,
        critic_secured=panel.critic_secured,
    )
