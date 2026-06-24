# 집행 전(시뮬 예측) vs 후(실측) 정성 비교 — 스케일 환산 없이 방향성만 판정
"""prediction(상대)·actual(절대)을 묶어 BeforeAfter로. 예측 없으면 UNKNOWN(시뮬 미연결).

판정은 클릭 축 단독: click_intent_rate(예측)↔ctr(실측)을 각자 기준선 통과 여부(boolean)로만
본다(스케일이 달라 직접 비교 금지, CLAUDE.md). 구매의도·신뢰도·거부율은 판정엔 안 쓰고
'왜 이런 결과일 수 있는지'를 설명하는 결정론 보조 해석(interpretation)으로만 쓴다.
"""

from __future__ import annotations

from domain.management.comparison.schemas import (
    BeforeAfter,
    BeforeAfterVerdict,
    PredictionSnapshot,
)
from domain.management.contracts.schemas import RealOutcome

#: 예측 "강함" — 클릭 의향률. 집행 권장 게이트 click_intent_rate >= 0.2 와 의도적으로 동일
#: (중복이지만 트랙 결합 회피 — 공용 constants 위치가 생기면 그곳으로 이전).
CLICK_INTENT_STRONG = 0.2
#: 실측 "양호" — CTR 1%.
CTR_STRONG = 0.01
#: 보조 해석 임계.
REJECTION_HIGH = 0.2  # 거부율 "높음"
TRUST_LOW = 3.0  # 신뢰도 "낮음" (1~5)
PURCHASE_HIGH = 3.5  # 구매의도 "높음"
PURCHASE_LOW = 2.5  # 구매의도 "낮음"

#: 보조 해석에 노출할 최대 신호 수.
_MAX_NOTES = 2


def _actual_strong(actual: RealOutcome) -> bool:
    """클릭 축 실측 양호 = CTR 기준 단독(ROAS는 구매 축이라 판정에서 제외)."""
    return actual.ctr >= CTR_STRONG


def _interpretation(prediction: PredictionSnapshot, act_strong: bool) -> str:
    """보조 KPI에서 두드러진 신호 상위 2개를 골라 해석 한 줄로 조립(결정론).

    v1 non-null 불변식 의존: purchase_intent·trust_avg·rejection_rate는 simulation_aggregates에서
    nullable=False이고 PredictionSnapshot도 비-Optional float라 None-skip 가드를 두지 않는다.
    향후 해당 KPI가 Optional로 바뀌면 여기에 None-skip 가드를 추가한다.
    """
    notes: list[str] = []
    if prediction.rejection_rate >= REJECTION_HIGH:
        notes.append(
            f"거부율 예측이 높음({prediction.rejection_rate * 100:.0f}%) — "
            "일부 소비자 거부감 가능, 소재 점검"
        )
    if prediction.trust_avg < TRUST_LOW:
        notes.append(
            f"신뢰도 예측이 낮음({prediction.trust_avg:.1f}/5) — 신뢰 보강(근거·리뷰) 검토"
        )
    if not act_strong and prediction.purchase_intent >= PURCHASE_HIGH:
        notes.append("클릭 유도는 약해도 구매 의향은 높음 — 랜딩·오퍼 점검")
    if prediction.purchase_intent < PURCHASE_LOW:
        notes.append(f"구매의도 예측이 낮음({prediction.purchase_intent:.1f}/5) — 전환 기대 보수적")
    return ". ".join(notes[:_MAX_NOTES])


def compute_before_after(
    campaign_id: str,
    name: str,
    prediction: PredictionSnapshot | None,
    actual: RealOutcome,
) -> BeforeAfter:
    """전(예측)·후(실측) 묶음 + 클릭 축 방향성 판정 + 보조 해석."""
    interpretation = ""
    if prediction is None:
        verdict, rationale = BeforeAfterVerdict.UNKNOWN, "시뮬 미연결 — 예측 데이터 없음"
    elif actual.impressions == 0:
        verdict, rationale = BeforeAfterVerdict.UNKNOWN, "집행 데이터 부족 — 노출 0"
    else:
        pred_strong = prediction.click_intent_rate >= CLICK_INTENT_STRONG
        act_strong = _actual_strong(actual)
        if pred_strong and act_strong:
            verdict, rationale = BeforeAfterVerdict.ALIGNED, "예측대로 좋음 — 실측이 뒷받침"
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
        interpretation = _interpretation(prediction, act_strong)
    return BeforeAfter(
        campaign_id=campaign_id,
        name=name,
        prediction=prediction,
        actual=actual,
        verdict=verdict,
        rationale=rationale,
        interpretation=interpretation,
    )
