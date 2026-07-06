"""🅰 기대 노출 곡선 + 기준선 + estimate 캘리브레이션 (BASELINE_UNAVAILABLE 포함).

기준선은 contracts/policy.py의 앵커·일중 곡선을 공유한다 — Mock과 같은 "정상"을
보지 않으면 정상 케이스가 오탐된다 (게이트 #5 오탐률 ≤5%).
"""

from domain.management.contracts.policy import CPM_ANCHOR_KRW, HOURLY_PACING

# 이상 판정 임계 — 화면 '탐지 기준' 표기와 판정 로직이 같은 값을 쓰도록 상수로 공유.
DEFICIT_THRESHOLD = 0.5  # 관측 노출 < 기대 × 이 비율 → 그 시간대는 '결핍'
MIN_CONSECUTIVE_HOURS = 2  # 결핍이 이 시간 이상 연속일 때만 이상(단발 노이즈 오탐 방지)


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
    deficit_threshold: float = DEFICIT_THRESHOLD,
    min_consecutive: int = MIN_CONSECUTIVE_HOURS,
) -> list[int]:
    """기대 대비 관측이 임계 미만인 시간대 반환.

    실시간 캠페인은 경과한 시간까지만 관측되므로, 종일 기대 곡선을 관측 길이에
    맞춰 정렬한다. observed가 expected보다 길면(24시간 초과 버킷) 진짜 정렬 오류다.

    가드레일: min_consecutive회 연속 관측을 충족한 구간만 이상으로 본다
    (단발 노이즈로 인한 오탐 방지).
    """
    if len(observed) > len(expected):
        raise ValueError(
            f"관측 시간 수({len(observed)})가 기대 곡선({len(expected)})보다 김 — 정렬 오류"
        )
    # observed가 더 짧은 건 정상(경과 시간까지만 관측) — 위에서 초과만 막았으니 strict=False
    flagged = [obs < exp * deficit_threshold for exp, obs in zip(expected, observed, strict=False)]

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
