# Meta 캠페인 생성 정책 — 최소예산 등을 Meta에서 실시간 조회해 자동 최신화한다.
"""캠페인 생성 정책 — 단일 진실원천(Single Source of Truth).

★ 원칙 (절대 규칙) ★
1. 실데이터는 휴리스틱·추측 금지 — 진짜 Meta 정책과 무조건 일치해야 한다.
   숫자(최소예산 등)는 Meta API에서 받거나 validate_only 실측으로 확인한 값만 쓴다.
2. Meta 정책이 바뀌면 프론트도 자동으로 바뀐다 — 이 모듈이 /campaign-policy로 내려주는
   값을 프론트가 그대로 렌더한다(프론트엔 정책 숫자·라벨 하드코딩 금지).
   → 정책 변경 시 여기 한 곳만 고치면 폼·검증이 동시에 따라온다.

min_daily_budget은 계정 통화 floor라 Meta가 바꾸면 실시간 조회로 자동 반영(+ 1h 캐시).
목표별 최소는 2026-06 validate_only 실측 결과 트래픽·리드 모두 floor와 동일(버퍼 없음).
Meta가 데이터로 노출하지 않는 특별카테고리·연령은 문서 기준값을 두되, 라벨까지 여기서 내려
프론트가 렌더한다(원칙 2). 새 거부가 보이면 writer 로깅으로 잡아 여기서 갱신한다.
"""

from __future__ import annotations

import time
from typing import Any

# Meta가 데이터로 노출하지 않는 정책 — 문서 기준 기본값. Meta 정책이 바뀌면 여기만 고치면
# /campaign-policy를 통해 프론트(폼)까지 자동 반영된다(프론트는 이 라벨을 그대로 렌더).
# value=Meta API special_ad_categories enum(고정), label=현재 표시명.
_SPECIAL_AD_CATEGORIES = [
    {"value": "NONE", "label": "없음"},
    {"value": "HOUSING", "label": "주택"},
    {"value": "EMPLOYMENT", "label": "고용"},
    # Meta가 2025년 '신용'→'금융 상품·서비스'로 확장·개명(API enum은 CREDIT 유지).
    {"value": "CREDIT", "label": "금융 상품·서비스"},
    {"value": "ISSUES_ELECTIONS_POLITICS", "label": "사회·선거·정치"},
]
# 특별 카테고리는 18~65 강제(Meta), 일반 광고는 더 낮게 가능 — 안전 기본은 18.
_AGE_MIN, _AGE_MAX = 18, 65

# 목표별 최소 일예산 = 계정 floor(min_daily_budget) 그대로.
# 2026-06 validate_only 실측: 트래픽·리드 광고세트 모두 floor(₩1,521)에서 생성 허용,
# floor 미만(예: ₩1,000)만 거부(code 100/subcode 1885272). 즉 별도 버퍼·목표별 가산 불필요.
# (리드는 floor에서도 생성은 되나 게재 효율은 예산이 클수록 좋음 — 그건 권장이지 최소가 아님.)
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
    # 목표별 최소 = Meta 계정 floor 그대로(휴리스틱·버퍼 금지). floor가 바뀌면 자동 반영.
    min_by_objective = {"traffic": floor, "leads": floor}
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
