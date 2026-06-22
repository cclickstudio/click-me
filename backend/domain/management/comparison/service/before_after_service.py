# 집행 전(시뮬 예측) vs 후(실측) 정성 비교 — 스케일 환산 없이 방향성만 판정
"""prediction(상대)·actual(절대)을 묶어 BeforeAfter로. 예측 없으면 UNKNOWN(시뮬 미연결).

예측은 0~1·1~5·0~100, 실측은 CTR·ROAS 등 절대값이라 수치 환산하지 않고(CLAUDE.md)
'예측이 좋다고 본 게 실제로 잘 나왔나'를 방향성으로만 본다.
"""

from __future__ import annotations

from domain.management.comparison.schemas import (
    BeforeAfter,
    BeforeAfterVerdict,
    PredictionSnapshot,
)
from domain.management.contracts.schemas import RealOutcome

#: 예측 "강함" 기준 — objective_fit 종합점수.
_PRED_STRONG_SCORE = 60
#: 실측 "양호" 기준 — ROAS≥1(전환가치 있을 때) 또는 CTR≥1%.
_ACTUAL_STRONG_CTR = 0.01
_ACTUAL_STRONG_ROAS = 1.0


def _actual_strong(actual: RealOutcome) -> bool:
    if actual.roas is not None:
        return actual.roas >= _ACTUAL_STRONG_ROAS
    return actual.ctr >= _ACTUAL_STRONG_CTR


def compute_before_after(
    campaign_id: str,
    name: str,
    prediction: PredictionSnapshot | None,
    actual: RealOutcome,
) -> BeforeAfter:
    """전(예측)·후(실측) 묶음 + 정성 방향성 판정."""
    if prediction is None:
        verdict, rationale = BeforeAfterVerdict.UNKNOWN, "시뮬 미연결 — 예측 데이터 없음"
    elif actual.impressions == 0:
        verdict, rationale = BeforeAfterVerdict.UNKNOWN, "집행 데이터 부족 — 노출 0"
    else:
        pred_strong = (prediction.objective_fit_score or 0) >= _PRED_STRONG_SCORE
        act_strong = _actual_strong(actual)
        if pred_strong and act_strong:
            verdict, rationale = BeforeAfterVerdict.ALIGNED, "예측대로 양호 — 실측이 뒷받침"
        elif pred_strong and not act_strong:
            verdict, rationale = (
                BeforeAfterVerdict.UNDERPERFORMED,
                "예측은 높았으나 실측은 약함 — 소재·타겟 점검",
            )
        elif not pred_strong and act_strong:
            verdict, rationale = (
                BeforeAfterVerdict.OVERPERFORMED,
                "예측보다 실측이 좋음 — 증액 검토",
            )
        else:
            verdict, rationale = BeforeAfterVerdict.ALIGNED, "예측대로 낮음 — 관망"
    return BeforeAfter(
        campaign_id=campaign_id,
        name=name,
        prediction=prediction,
        actual=actual,
        verdict=verdict,
        rationale=rationale,
    )
