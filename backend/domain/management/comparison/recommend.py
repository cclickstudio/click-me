# 🅰 리프트 판정 → 추천 액션 신호 (순수 함수, 외부 의존 0)
"""LiftResult의 verdict를 권고 액션으로 매핑한다.

원칙: "줄이는 건 자율, 늘리는 건 승인"(ActionTier 주석)과 결이 같다.
- PASS  광고가 증분 도달을 크게 만듦 → 증액 검토(SCALE_UP, INCREASE_BUDGET 힌트)
- CAUTION 약한 증분 → 유지·관찰(HOLD, 힌트 없음)
- FAIL  증분 미미 → 중단·감액 검토(PAUSE, PAUSE_CAMPAIGN 힌트)

제안 생성·Tier 판정은 🅱 책임 — 여기는 분석 권고만 낸다(경계 유지).
"""

from __future__ import annotations

from datetime import UTC, datetime

from domain.management.comparison.schemas import (
    ComparisonRecommendation,
    LiftResult,
    LiftVerdict,
    RecommendedAction,
)

# verdict → (권고 액션, 🅱 action_type 힌트)
_VERDICT_MAP: dict[LiftVerdict, tuple[RecommendedAction, str]] = {
    LiftVerdict.PASS: (RecommendedAction.SCALE_UP, "INCREASE_BUDGET"),
    LiftVerdict.CAUTION: (RecommendedAction.HOLD, ""),
    LiftVerdict.FAIL: (RecommendedAction.PAUSE, "PAUSE_CAMPAIGN"),
}

_RATIONALE: dict[RecommendedAction, str] = {
    RecommendedAction.SCALE_UP: "광고 증분 도달이 충분(×3+) — 증액 검토",
    RecommendedAction.HOLD: "증분이 약함(×1.5~3) — 유지·관찰",
    RecommendedAction.PAUSE: "증분 미미(<×1.5) — 중단·감액 검토",
}


def recommend_action(lift: LiftResult) -> ComparisonRecommendation:
    """LiftResult를 🅰 추천 신호로 변환. 미등록 verdict는 보수적으로 HOLD."""
    action, action_type = _VERDICT_MAP.get(lift.verdict, (RecommendedAction.HOLD, ""))
    return ComparisonRecommendation(
        post_id=lift.post_id,
        verdict=lift.verdict,
        recommended_action=action,
        suggested_action_type=action_type,
        reach_lift_ratio=lift.reach_lift_ratio,
        rationale=_RATIONALE[action],
        computed_at=datetime.now(UTC),
    )
