# Meta(소셜피드) 도달 가능성 — KISDI 노출맥락에서 소셜피드 비중 산출·노출 후보 필터(LLM✗)
#
# Meta 광고는 스마트폰/PC의 SNS·동영상 피드에서 노출된다. 그 외 맥락(TV·신문·문화시설)은 무관.
# ① 가중에 쓸 셀별 소셜피드 비중 ② 반응 노출맥락 선택을 모은다.
# generic SNS/동영상 기준(브랜드 비식별) — "Meta 특정"은 외부 침투율 보정으로 추후(Tier2).
from __future__ import annotations

import random
from typing import Any

# KISDI 행위(activity)·매체(medium) 대분류명 — build_media_behavior.py 의 그룹명과 정합.
SOCIAL_FEED_ACTIVITIES = frozenset({"SNS", "동영상/개인방송"})
SOCIAL_FEED_MEDIA = frozenset({"스마트폰/휴대폰", "PC"})


def is_social_context(activity: str | None, medium: str | None) -> bool:
    """소셜피드(Meta 노출 가능) 맥락인가 — 소셜 행위 × 스마트폰/PC 매체일 때만."""
    return activity in SOCIAL_FEED_ACTIVITIES and medium in SOCIAL_FEED_MEDIA


def cell_social_reach(cell: dict[str, Any] | None) -> float | None:
    """셀(연령×성별)의 소셜피드 노출 비중 = 노출맥락 확률 p 중 소셜 맥락의 합(0~1).

    노출 데이터가 없으면(평면 폴백 등) None — 호출자는 가중을 건드리지 않아 중립 처리한다.
    """
    if not cell:
        return None
    exposure = cell.get("exposure") or []
    if not exposure:
        return None
    return sum(
        e.get("p", 0.0) for e in exposure if is_social_context(e.get("activity"), e.get("medium"))
    )


def pick_social_exposure(
    candidates: list[dict[str, Any]], rng: random.Random
) -> dict[str, Any] | None:
    """노출 후보 중 소셜피드 맥락만 골라 하나 선택. 소셜 후보가 없으면 None(호출자가 폴백)."""
    social = [c for c in candidates if is_social_context(c.get("activity"), c.get("medium"))]
    if not social:
        return None
    return rng.choice(social)
