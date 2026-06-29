# 캘리브레이션 앵커 순위 일치율(concordance)·요약 로직 단위 테스트
from domain.management.comparison.calibration import (
    UNLOCK_THRESHOLD,
    CalibrationAnchor,
    build_summary,
    pairwise_concordance,
)


def _anchor(name: str, click: float, ctr: float, purchase: float, cvr: float | None):
    return CalibrationAnchor(
        campaign_id=name,
        name=name,
        source="sim",
        predicted_click_intent=click,
        actual_ctr=ctr,
        predicted_purchase_intent=purchase,
        actual_cvr=cvr,
        predicted_rejection=0.1,
        actual_impressions=1000,
        actual_spend_krw=10000,
    )


def test_concordance_perfect():
    # 예측 순위와 실측 순위가 완전히 같음 → 1.0
    pairs = [(0.8, 0.07), (0.5, 0.05), (0.2, 0.01)]
    assert pairwise_concordance(pairs) == 1.0


def test_concordance_inverted():
    # 완전 역순 → 0.0
    pairs = [(0.8, 0.01), (0.2, 0.07)]
    assert pairwise_concordance(pairs) == 0.0


def test_concordance_mixed():
    # 3쌍 중 2개 일치, 1개 불일치 → 2/3 (중간 앵커의 실측만 살짝 낮음)
    pairs = [(0.8, 0.07), (0.5, 0.05), (0.2, 0.06)]
    val = pairwise_concordance(pairs)
    assert val is not None and abs(val - 2 / 3) < 1e-9


def test_concordance_ties_and_empty():
    assert pairwise_concordance([]) is None
    assert pairwise_concordance([(0.5, 0.05)]) is None  # 1개 — 비교 불가
    assert pairwise_concordance([(0.5, 0.05), (0.5, 0.07)]) is None  # 예측 동점 — 비교 불가


def test_build_summary_unlock_and_purchase_skip():
    anchors = [
        _anchor("a", 0.8, 0.07, 4.0, 0.30),
        _anchor("b", 0.5, 0.05, 3.0, None),  # cvr None → 구매 축 비교 제외
        _anchor("c", 0.2, 0.01, 2.0, 0.10),
    ]
    s = build_summary(anchors)
    assert s.n == 3
    assert s.concordance_click == 1.0  # click↔ctr 완전 일치
    # 구매 축은 None 제외하면 a·c 2건 → 4.0>2.0, 0.30>0.10 일치 → 1.0
    assert s.concordance_purchase == 1.0
    assert s.unlock_threshold == UNLOCK_THRESHOLD
    assert s.unlocked is (UNLOCK_THRESHOLD <= 3)


def test_build_summary_empty():
    s = build_summary([])
    assert s.n == 0
    assert s.concordance_click is None
    assert s.unlocked is False
