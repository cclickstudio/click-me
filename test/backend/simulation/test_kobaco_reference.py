# KOBACO 참고치 조회 헬퍼 단위 테스트 — 매핑 히트/미스, None 입력 LLM✗
from __future__ import annotations

from domain.simulation.tools.aggregation.kobaco_reference import lookup_kobaco_reference


def test_lookup_maps_declared_category_to_kobaco_key():
    ref = lookup_kobaco_reference("뷰티/미용/화장품")
    assert ref is not None
    assert ref["declared_category"] == "뷰티/미용/화장품"
    assert ref["kobaco_category"] == "뷰티"
    assert ref["tv_ad_influence_pct"] is not None


def test_lookup_returns_none_for_unmapped_category():
    assert lookup_kobaco_reference("전체분류") is None


def test_lookup_returns_none_for_empty_input():
    assert lookup_kobaco_reference(None) is None
    assert lookup_kobaco_reference("") is None


def test_lookup_reference_includes_scale_caveat_note():
    ref = lookup_kobaco_reference("여행/스포츠/취미")
    assert ref is not None
    assert "척도" in ref["note"]
