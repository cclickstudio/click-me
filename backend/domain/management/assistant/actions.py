# 행동 의도 → 추천 액션 (제안만 — 실행은 승인→executor 경로)
"""질문에서 행동 의도(일시중지·게재시작·증액·감액·소재교체)를 키워드로 감지해 추천 액션을 만든다.

어시스턴트는 write를 트리거하지 않는다. Tier는 정책 단일원천(TIER_POLICY)에서 읽고,
자동승인 한도(AUTO_APPROVE_MAX_TIER) 초과면 사람 승인 필요(requires_approval=True)로 표시.
"""

from __future__ import annotations

from domain.management.assistant.contracts import SuggestedAction
from domain.management.contracts.enums import ActionTier
from domain.management.contracts.policy import AUTO_APPROVE_MAX_TIER, TIER_POLICY

#: 키워드 → action_type (구체적 의도 우선 정렬)
_RULES: list[tuple[tuple[str, ...], str]] = [
    (("일시중지", "멈춰", "멈춤", "중단", "꺼", "끄기", "정지"), "PAUSE_CAMPAIGN"),
    (("게재 시작", "게재시작", "켜", "활성화", "시작해", "내보내"), "ACTIVATE_CAMPAIGN"),
    (("증액", "예산 올", "예산올", "올려", "늘려", "늘리"), "INCREASE_BUDGET"),
    (("감액", "예산 줄", "줄여", "내려", "낮춰"), "DECREASE_BUDGET"),
    (("소재", "크리에이티브", "교체", "바꿔", "갈아"), "REPLACE_CREATIVE"),
]

_RATIONALE = {
    "PAUSE_CAMPAIGN": "게재를 중단합니다",
    "ACTIVATE_CAMPAIGN": "게재를 시작합니다(실과금)",
    "INCREASE_BUDGET": "예산을 증액합니다",
    "DECREASE_BUDGET": "예산을 감액합니다",
    "REPLACE_CREATIVE": "광고 소재를 교체합니다",
}


def suggest_action(question: str, campaign_id: str | None = None) -> SuggestedAction | None:
    """행동 의도가 있으면 추천 액션, 없으면 None. 실행하지 않는다(제안만)."""
    for keywords, action_type in _RULES:
        if any(k in question for k in keywords):
            tier = TIER_POLICY.get(action_type, ActionTier.TIER_3)
            requires = tier not in (ActionTier.TIER_0, AUTO_APPROVE_MAX_TIER)
            hint = "사람 승인 필요" if requires else "낮은 위험(자동 승인 한도 내)"
            return SuggestedAction(
                action_type=action_type,
                target_campaign_id=campaign_id,
                tier=tier.name,
                requires_approval=requires,
                rationale=f"{_RATIONALE[action_type]} — {hint}. 실행은 승인 경로에서 확인하세요.",
            )
    return None
