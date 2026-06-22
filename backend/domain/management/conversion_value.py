# 비이커머스 전환의 통계가치 기반 추정 ROAS — 고객이 입력한 전환 1건 가치로 환산한다.
"""전환 가치 환산 — 측정된 매출이 없는 리드·가입·설치 캠페인의 ROAS를 추정한다.

reader는 Meta 실측만 싣는다(구매 외 전환의 ROAS는 None). 그 빈자리를 고객이 입력한
"전환 1건 가치(통계정보)"로 채우는 책임이 여기 있다. 산출값은 실측이 아니라 추정이며,
호출측은 반드시 '추정'으로 표기해야 한다(합성 금지·정직 원칙).
"""

from __future__ import annotations


def estimate_roas(
    conversions: int | None,
    conversion_value_krw: int | None,
    spend_krw: int,
) -> float | None:
    """전환 건수 × 입력 전환가치 ÷ 지출 = 추정 ROAS (없으면 None).

    전환 가치는 고객 비즈니스 통계에서 온다 — 예: 고객 생애가치 × 리드→고객 전환율.
    전환·가치·지출 중 하나라도 비면 추정 불가(None) — 빈자리를 0으로 메우지 않는다.
    """
    if not conversions or not conversion_value_krw or not spend_krw:
        return None
    return conversions * conversion_value_krw / spend_krw
