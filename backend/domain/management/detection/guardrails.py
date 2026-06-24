"""🅰 가드레일 — INSUFFICIENT_DATA vs DELIVERY_ANOMALY 분리 + grace.

게이트 #6: baseline/estimate 부재(BASELINE_UNAVAILABLE)가 자동 pause(이상)로 이어지지
않는다. 판단을 못 하는 상태(데이터 부족)와 이상이 확인된 상태를 절대 섞지 않는다.
2회 연속 관측 가드레일은 exposure_model.find_anomaly_window가 담당.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

_MIN_OBSERVED_HOURS = 3  # grace — 관측 시간이 이보다 적으면 판단 보류


class GuardVerdict(StrEnum):
    NORMAL = "normal"
    INSUFFICIENT_DATA = "insufficient_data"  # 판단 보류 — 자동 액션 금지
    DELIVERY_ANOMALY = "delivery_anomaly"


@dataclass(frozen=True)
class GuardResult:
    verdict: GuardVerdict
    anomaly_hours: list[int] = field(default_factory=list)
    reason: str = ""


def evaluate(
    expected: list[float],
    observed: list[int],
    *,
    anomaly_hours: list[int],
    baseline_available: bool = True,
) -> GuardResult:
    """가드레일 판정. 데이터 부족이면 이상으로 승격하지 않는다."""
    if not baseline_available:
        return GuardResult(
            GuardVerdict.INSUFFICIENT_DATA,
            reason="baseline/estimate 없음 — 기대치 산출 불가, 자동 액션 보류",
        )

    observed_hours = sum(1 for o in observed if o > 0)
    if observed_hours < _MIN_OBSERVED_HOURS:
        return GuardResult(
            GuardVerdict.INSUFFICIENT_DATA,
            reason=f"관측 {observed_hours}시간 < grace {_MIN_OBSERVED_HOURS}시간 — 판단 보류",
        )

    if anomaly_hours:
        return GuardResult(
            GuardVerdict.DELIVERY_ANOMALY,
            anomaly_hours=anomaly_hours,
            reason=f"{len(anomaly_hours)}시간 기대 대비 미달 (2회 연속 관측 충족)",
        )

    return GuardResult(GuardVerdict.NORMAL, reason="기대 곡선 정상 범위")
