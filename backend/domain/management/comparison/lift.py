# 🅰 증분 리프트 계산 — 순수 함수, 외부 의존 0
"""오가닉 대비 광고가 만든 증분 도달·노출 + 판정.

판정 기준(시안과 동일): 도달 배수 ≥ ×3 통과 · ×1.5~×3 주의 · 그 미만 미달.
신뢰구간(CI)은 집계 데이터만으로 산출 불가 → v1 제외(exploratory).
"""

from __future__ import annotations

from datetime import UTC, datetime

from domain.management.comparison.schemas import LiftResult, LiftVerdict, PostInsights

_PASS_RATIO = 3.0
_CAUTION_RATIO = 1.5


def _verdict(ratio: float) -> LiftVerdict:
    if ratio >= _PASS_RATIO:
        return LiftVerdict.PASS
    if ratio >= _CAUTION_RATIO:
        return LiftVerdict.CAUTION
    return LiftVerdict.FAIL


def compute_lift(organic: PostInsights, paid: PostInsights) -> LiftResult:
    """오가닉↔광고 증분 효과 산출. 오가닉 도달 0이면 분모 1로 보수 처리."""
    denom = max(organic.reach, 1)
    ratio = paid.reach / denom
    return LiftResult(
        post_id=organic.post_id,
        organic=organic,
        paid=paid,
        reach_lift_abs=paid.reach - organic.reach,
        reach_lift_ratio=round(ratio, 3),
        impressions_lift_abs=paid.impressions - organic.impressions,
        verdict=_verdict(ratio),
        computed_at=datetime.now(UTC),
    )
