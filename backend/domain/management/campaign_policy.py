# Meta 캠페인 생성 정책 — 최소예산 등을 Meta에서 실시간 조회해 자동 최신화한다.
"""캠페인 생성 정책. 핵심 원칙 — 정책을 코드에 박지 않고 Meta API에서 가져온다.

min_daily_budget은 계정 통화 floor라 Meta가 바꾸면 자동 반영된다(실시간 조회 + 캐시).
목표별 최소·특별 카테고리·연령처럼 Meta가 숫자로 노출하지 않는 부분은 문서화된 기본값을 두고,
실패 로깅(writer)으로 새 거부가 보이면 빠르게 갱신한다.
"""

from __future__ import annotations

import time
from typing import Any

# Meta가 데이터로 노출하지 않는 정책 — 문서 기준 기본값. 바뀌면 여기만 수정.
_SPECIAL_AD_CATEGORIES = ["NONE", "HOUSING", "EMPLOYMENT", "CREDIT", "ISSUES_ELECTIONS_POLITICS"]
_AGE_MIN, _AGE_MAX = 18, 65

# 목표별 안전 최소 일예산(KRW). 리드(전환 최적화)는 floor보다 높은 최소를 요구한다.
# Meta floor가 이 값을 넘으면 floor+버퍼를 따른다(아래 산출).
_STATIC_MIN_KRW = {"traffic": 2_000, "leads": 10_000}
_FALLBACK_FLOOR_KRW = 1_521  # Meta 조회 실패 시 폴백(KRW 계정 floor, 2026-06 실측)

_TTL_SEC = 3600  # 1시간 — 정책은 자주 안 바뀜
_cache: dict[str, float] = {}


async def get_campaign_policy(reader: Any) -> dict[str, Any]:
    """캠페인 생성 정책 — 최소예산은 Meta에서 실시간 조회(1h 캐시), 나머지는 기본값.

    조회 실패(목 reader·네트워크 등)해도 폴백으로 항상 유효한 정책을 돌려준다(폼이 떠야 함).
    """
    now = time.time()
    if "floor" not in _cache or now - _cache.get("at", 0) > _TTL_SEC:
        try:
            floor = await reader.get_min_daily_budget() or _FALLBACK_FLOOR_KRW
        except Exception:  # noqa: BLE001 — 조회 실패해도 폴백으로 폼은 떠야 한다
            floor = _FALLBACK_FLOOR_KRW
        _cache["floor"], _cache["at"] = float(floor), now
    floor = int(_cache["floor"])
    # Meta floor가 정적 최소를 넘으면 floor+버퍼를 따른다(자동 최신화).
    min_by_objective = {obj: max(static, floor + 500) for obj, static in _STATIC_MIN_KRW.items()}
    return {
        "min_daily_budget_krw": floor,
        "min_by_objective_krw": min_by_objective,
        "special_ad_categories": _SPECIAL_AD_CATEGORIES,
        "age_min": _AGE_MIN,
        "age_max": _AGE_MAX,
    }


def min_daily_budget_for(objective: str, policy: dict[str, Any]) -> int:
    """정책에서 목표별 최소 일예산을 꺼낸다 (검증·표시 공용)."""
    return int(policy["min_by_objective_krw"].get(objective, policy["min_daily_budget_krw"]))
