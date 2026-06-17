"""🅰 기대 노출 곡선 + 기준선 + estimate 캘리브레이션 (BASELINE_UNAVAILABLE 포함).

기준선은 contracts/policy.py의 앵커·일중 곡선을 공유한다 — Mock과 같은 "정상"을
보지 않으면 정상 케이스가 오탐된다 (게이트 #5 오탐률 ≤5%).
"""

from domain.management.contracts.policy import CPM_ANCHOR_KRW, HOURLY_PACING


def expected_hourly_impressions(
    daily_budget_krw: int,
    cpm_anchor_krw: int = CPM_ANCHOR_KRW,
) -> list[float]:
    """예산·CPM 앵커 기반 시간별 기대 노출 곡선."""
    daily_total = daily_budget_krw / cpm_anchor_krw * 1000
    return [daily_total * share for share in HOURLY_PACING]


def find_anomaly_window(
    expected: list[float],
    observed: list[int],
    deficit_threshold: float = 0.5,
    min_consecutive: int = 2,
) -> list[int]:
    """기대 대비 관측이 임계 미만인 시간대 반환.

    가드레일: min_consecutive회 연속 관측을 충족한 구간만 이상으로 본다
    (단발 노이즈로 인한 오탐 방지).
    """
    flagged = [obs < exp * deficit_threshold for exp, obs in zip(expected, observed, strict=True)]

    window: list[int] = []
    run: list[int] = []
    for hour, is_low in enumerate(flagged):
        if is_low:
            run.append(hour)
        else:
            if len(run) >= min_consecutive:
                window.extend(run)
            run = []
    if len(run) >= min_consecutive:
        window.extend(run)
    return window
