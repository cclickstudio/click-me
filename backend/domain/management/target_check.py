# 목표 대비 성과 미달 판정 — 고객이 입력한 목표 ROAS에 실제 성과가 못 미치는지(이상치).
"""성과 목표 판정 — 실 캠페인의 ROAS가 고객 목표 대비 미달인지 본다.

게재 고장 진단(detection/deterministic_dx, 고장 주입 데모)과는 별개의 실데이터 판정.
'이 정도가 안 나오면 이상하다'의 기준선을 고객이 직접 정한다(멘토 피드백 ②).
"""

from __future__ import annotations

#: 목표의 이 비율 미만이면 '미달' — 약간의 변동은 허용(목표 100%를 빡빡하게 보지 않음).
TARGET_MISS_RATIO: float = 0.7


def is_target_missed(roas: float | None, target_roas: float | None) -> bool:
    """실제 ROAS가 목표의 70% 미만이면 True (둘 중 하나라도 없으면 판정 불가 → False).

    여기서 roas는 실측·추정 어느 쪽이어도 된다 — '실제 나온 ROAS'를 목표와 견준다.
    """
    if roas is None or not target_roas:
        return False
    return roas < target_roas * TARGET_MISS_RATIO
