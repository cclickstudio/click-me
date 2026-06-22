# Tier 3 브랜드 보조인지율 룩업 — 광고 텍스트에 등장한 브랜드를 brand_awareness.json에서 찾아 부착
#
# 재검색 없음 — interpret_ad에서 1회 룩업해 공유 해석(structured_analysis)에 부착.
# 미수록·미식별이면 None → 호출자는 아무것도 부착하지 않고 Tier 2(LLM 추정·세대 게이팅)로 폴백.
from __future__ import annotations

from typing import Any

from domain.simulation.data.simulation import loader


def _normalize(s: str) -> str:
    """공백 제거 + 소문자 — 브랜드명 부분일치 비교용."""
    return "".join(str(s).split()).lower()


def lookup_brand_awareness(
    brand_hint: str | None,
    *,
    data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """광고 텍스트(brand_hint)에서 수록 브랜드를 찾아 연령별 인지율을 반환. 없으면 None.

    brand_hint 는 광고 제목·감지 메시지 등 브랜드명이 들어있을 만한 텍스트. 각 브랜드 키·별칭이
    이 텍스트에 부분일치하면 그 브랜드의 awareness_by_age 를 돌려준다. data 미지정 시 JSON 로드.
    """
    if not brand_hint:
        return None
    data = data if data is not None else loader.load_brand_awareness()
    brands = data.get("brands") or {}
    if not brands:
        return None
    hint = _normalize(brand_hint)
    for name, info in brands.items():
        candidates = [name, *(info.get("aliases") or [])]
        if any(c and _normalize(c) in hint for c in candidates):
            awareness = info.get("awareness_by_age")
            if awareness:
                return {
                    "awareness_by_age": awareness,
                    "awareness_brand": name,
                    "awareness_source": info.get("source"),
                    "awareness_tier": 3,
                }
    return None
