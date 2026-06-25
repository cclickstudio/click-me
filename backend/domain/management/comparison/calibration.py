# 베이스라인 앵커 — 집행된 광고의 (시뮬 예측, 실 Meta 실측)을 모아 방향성 정합을 계산
"""calibration 준비 단계. 예측·실측은 스케일이 달라 절대 환산 금지(CLAUDE.md) →
앵커들 사이의 '순위 일치율'(pairwise concordance)로만 시뮬의 방향성 타당성을 본다.

앵커 1건 = 연결된(simulation_id) 캠페인 1건의 예측↔실측 쌍. 캠페인이 늘면 앵커도 누적된다
(별도 영속 없이 created_campaigns·simulation_aggregates 조인으로 매번 모은다).
"""

from __future__ import annotations

from domain.management.comparison.schemas import Contract

#: 앵커 N개 이상이면 calibration(절대 환산) 검토 가능 — 그 전엔 방향성만(탐색적).
UNLOCK_THRESHOLD = 5


class CalibrationAnchor(Contract):
    """집행된 광고 1건의 예측↔실측 앵커 (절대 비교 금지 — 순위 정합에만 사용)."""

    campaign_id: str
    name: str
    source: str  # 예측 출처 (sim | mock)
    predicted_click_intent: float  # 0~1
    actual_ctr: float  # 0~1
    predicted_purchase_intent: float  # 1~5
    actual_cvr: float | None  # 0~1 (전환 추적 전이면 None)
    predicted_rejection: float  # 0~1
    actual_impressions: int
    actual_spend_krw: int


class CalibrationSummary(Contract):
    """앵커 집합의 방향성 정합 요약."""

    n: int
    concordance_click: float | None  # 예측 클릭의향률 vs 실측 CTR 순위 일치율(0~1)
    concordance_purchase: float | None  # 예측 구매의도 vs 실측 CVR 순위 일치율(0~1)
    unlock_threshold: int
    unlocked: bool  # N이 임계 이상이라 calibration 검토 가능


def pairwise_concordance(pairs: list[tuple[float, float]]) -> float | None:
    """(예측, 실측) 쌍들의 순위 일치율 — 모든 두 앵커 비교에서 같은 방향이면 일치(Kendall 일치율).

    동점(한쪽이라도 차이 0)은 비교 불가로 제외. 비교 가능한 쌍이 없으면 None.
    """
    comparable = concordant = 0
    n = len(pairs)
    for i in range(n):
        for j in range(i + 1, n):
            dp = pairs[i][0] - pairs[j][0]
            da = pairs[i][1] - pairs[j][1]
            if dp == 0 or da == 0:
                continue
            comparable += 1
            if (dp > 0) == (da > 0):
                concordant += 1
    return concordant / comparable if comparable else None


def build_summary(anchors: list[CalibrationAnchor]) -> CalibrationSummary:
    """앵커 목록 → 클릭/구매 축 순위 일치율 + 해금 진행."""
    click_pairs = [(a.predicted_click_intent, a.actual_ctr) for a in anchors]
    purchase_pairs = [
        (a.predicted_purchase_intent, a.actual_cvr) for a in anchors if a.actual_cvr is not None
    ]
    return CalibrationSummary(
        n=len(anchors),
        concordance_click=pairwise_concordance(click_pairs),
        concordance_purchase=pairwise_concordance(purchase_pairs),
        unlock_threshold=UNLOCK_THRESHOLD,
        unlocked=len(anchors) >= UNLOCK_THRESHOLD,
    )
