# 시뮬 결과에 KOBACO(2019 MCR 실측) 참고치를 붙이는 조회 전용 헬퍼 — 값 병합·환산 없음
"""광고의 선언 카테고리(SIM_CATEGORIES 15종)를 kobaco_benchmarks.json 10종 키로 근사 매핑해
참고치를 찾는다. 우리 KPI(1~5점·0~1 비율)와 척도가 달라 절대 비교·환산은 하지 않고,
카테고리 간 상대 순위 참고용 원문 그대로 리포트에 함께 보여준다(§4대 KPI 규칙)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_KOBACO_PATH = Path(__file__).resolve().parents[4] / "data" / "kobaco_benchmarks.json"
_cache: dict[str, Any] | None = None

# 근사 매핑 — SIM_CATEGORIES(15종, frontend simCategories.ts) → kobaco_benchmarks.json 키(10종).
# 1:1 대응이 아니므로 탐색적 참고치임을 화면에 항상 함께 표기한다.
_CATEGORY_MAP: dict[str, str] = {
    "요식업/식음료": "식품",
    "의류/패션/쇼핑몰": "패션",
    "뷰티/미용/화장품": "뷰티",
    "의료/제약/복지": "기타",
    "여행/스포츠/취미": "여행",
    "교육/엔터테인먼트/유튜버": "교육",
    "생활/편의서비스": "금융",
    "생활용품/가구/가전제품": "생활용품",
    "출산/유아동": "기타",
    "반려/애완용품": "기타",
    "차량/오토": "기타",
    "인테리어/건축/부동산": "생활용품",
    "과학/환경/법률": "기타",
    "IT/플랫폼/APP": "전자제품",
}


def _load() -> dict[str, Any]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_KOBACO_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 파일 없으면 빈 값으로 진행(회귀 0)
            _cache = {}
    return _cache


def lookup_kobaco_reference(product_category: str | None) -> dict[str, Any] | None:
    """선언 카테고리로 KOBACO 참고치를 찾는다. 매핑 불가·데이터 없으면 None(리포트에서 생략)."""
    if not product_category:
        return None
    kobaco_key = _CATEGORY_MAP.get(product_category.strip())
    if not kobaco_key:
        return None
    bench = _load().get(kobaco_key)
    if not bench:
        return None
    return {
        "declared_category": product_category,
        "kobaco_category": kobaco_key,
        "purchase_intent_pct": bench.get("purchase_intent_pct"),
        "tv_ad_influence_pct": bench.get("tv_ad_influence_pct"),
        "note": "2019 KOBACO MCR 실측 — 카테고리 근사 매핑, 척도가 달라 방향·상대크기만 참고",
    }
