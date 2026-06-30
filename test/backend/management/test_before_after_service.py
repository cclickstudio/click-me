# compute_before_after — 클릭 축 4상태 판정 + 결정론 보조 해석
from datetime import UTC, datetime

from domain.management.comparison.schemas import (
    BeforeAfterVerdict,
    PredictionSnapshot,
)
from domain.management.comparison.service.before_after_service import compute_before_after
from domain.management.contracts.schemas import RealOutcome

_NOW = datetime.now(UTC)


def _pred(click_intent_rate=0.5, purchase_intent=3.0, trust_avg=4.0, rejection_rate=0.05):
    # 보조 KPI 기본값은 어떤 해석 규칙도 발화하지 않는 중립값.
    return PredictionSnapshot(
        ad_id="ad_1",
        click_intent_rate=click_intent_rate,
        purchase_intent=purchase_intent,
        trust_avg=trust_avg,
        rejection_rate=rejection_rate,
        as_of=_NOW,
        source="sim",
    )


def _actual(ctr=0.02, impressions=1000, cvr=None):
    return RealOutcome(
        campaign_id="m1",
        impressions=impressions,
        reach=900,
        spend_krw=10_000,
        ctr=ctr,
        cpc_krw=500,
        cpm_krw=3000,
        cvr=cvr,
        as_of=_NOW,
    )


# ── 4상태 매트릭스 (pred_strong: cir>=0.2 / act_strong: ctr>=0.01) ──


def test_pred_strong_act_strong_aligned_good():
    ba = compute_before_after("m1", "C", _pred(click_intent_rate=0.5), _actual(ctr=0.02))
    assert ba.verdict == BeforeAfterVerdict.ALIGNED
    assert "예측대로 좋음" in ba.rationale


def test_pred_strong_act_weak_underperformed():
    ba = compute_before_after("m1", "C", _pred(click_intent_rate=0.5), _actual(ctr=0.005))
    assert ba.verdict == BeforeAfterVerdict.UNDERPERFORMED


def test_pred_weak_act_strong_overperformed():
    ba = compute_before_after("m1", "C", _pred(click_intent_rate=0.1), _actual(ctr=0.02))
    assert ba.verdict == BeforeAfterVerdict.OVERPERFORMED


def test_pred_weak_act_weak_aligned_low():
    ba = compute_before_after("m1", "C", _pred(click_intent_rate=0.1), _actual(ctr=0.005))
    assert ba.verdict == BeforeAfterVerdict.ALIGNED
    assert "예측대로 낮음" in ba.rationale


# ── UNKNOWN 가드 (2종) ──


def test_no_prediction_unknown():
    ba = compute_before_after("m1", "C", None, _actual())
    assert ba.verdict == BeforeAfterVerdict.UNKNOWN
    assert "시뮬 미연결" in ba.rationale


def test_zero_impressions_unknown():
    ba = compute_before_after("m1", "C", _pred(), _actual(impressions=0))
    assert ba.verdict == BeforeAfterVerdict.UNKNOWN
    assert "노출 0" in ba.rationale


# ── 구매 축 방향성 배지용 파생 필드 ──


def test_purchase_direction_strong_when_purchase_intent_and_cvr_cross_baselines():
    ba = compute_before_after("m1", "C", _pred(purchase_intent=3.5), _actual(cvr=0.02))
    assert ba.purchase_pred_strong is True
    assert ba.purchase_act_strong is True


def test_purchase_prediction_weak_below_purchase_intent_baseline():
    ba = compute_before_after("m1", "C", _pred(purchase_intent=3.4), _actual(cvr=0.02))
    assert ba.purchase_pred_strong is False


def test_purchase_actual_unknown_when_cvr_is_null():
    ba = compute_before_after("m1", "C", _pred(purchase_intent=3.5), _actual(cvr=None))
    assert ba.purchase_act_strong is None


def test_purchase_prediction_unknown_when_prediction_is_missing():
    ba = compute_before_after("m1", "C", None, _actual(cvr=0.02))
    assert ba.purchase_pred_strong is None
    assert ba.purchase_act_strong is None


def test_purchase_direction_does_not_change_click_axis_verdict():
    ba = compute_before_after(
        "m1", "C", _pred(click_intent_rate=0.5, purchase_intent=3.5), _actual(ctr=0.005, cvr=0.03)
    )
    assert ba.verdict == BeforeAfterVerdict.UNDERPERFORMED


# ── 보조 해석 (결정론) ──


def test_interpretation_high_rejection():
    ba = compute_before_after("m1", "C", _pred(rejection_rate=0.25), _actual(ctr=0.02))
    assert "거부율" in ba.interpretation


def test_interpretation_low_trust():
    ba = compute_before_after("m1", "C", _pred(trust_avg=2.5), _actual(ctr=0.02))
    assert "신뢰도" in ba.interpretation


def test_interpretation_actual_weak_high_purchase():
    # act_strong == False and purchase_intent >= 3.5
    ba = compute_before_after("m1", "C", _pred(purchase_intent=4.0), _actual(ctr=0.005))
    assert "구매 의향은 높음" in ba.interpretation


def test_interpretation_low_purchase():
    ba = compute_before_after("m1", "C", _pred(purchase_intent=2.0), _actual(ctr=0.02))
    assert "구매의도 예측이 낮음" in ba.interpretation


def test_interpretation_top_two_only():
    # rule1(거부율)·rule2(신뢰도)·rule4(구매의도 낮음) 매칭 → 상위 2개만.
    ba = compute_before_after(
        "m1", "C", _pred(rejection_rate=0.25, trust_avg=2.5, purchase_intent=2.0), _actual(ctr=0.02)
    )
    assert "거부율" in ba.interpretation
    assert "신뢰도" in ba.interpretation
    assert "구매의도 예측이 낮음" not in ba.interpretation


def test_interpretation_none_empty():
    ba = compute_before_after("m1", "C", _pred(), _actual(ctr=0.02))
    assert ba.interpretation == ""
