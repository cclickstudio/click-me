# Tier 3 브랜드 인지율 룩업·반응 주입 단위 테스트 — 데이터 없으면 폴백(현 동작 보존)
from __future__ import annotations

from domain.simulation.adapters.gemini.reaction import _awareness_band, _awareness_lines
from domain.simulation.contracts.schemas import AdInterpretation
from domain.simulation.data.simulation import loader
from domain.simulation.tools.brand_awareness import lookup_brand_awareness

_FIXTURE = {
    "brands": {
        "더미브랜드": {
            "aliases": ["DummyBrand"],
            "awareness_by_age": {"20-29": 0.8, "60-69": 0.2},
            "source": "테스트",
        }
    }
}


def test_lookup_none_when_no_hint_or_empty() -> None:
    assert lookup_brand_awareness(None, data=_FIXTURE) is None
    assert lookup_brand_awareness("아무거나", data={"brands": {}}) is None
    # 기본 JSON은 brands 비어 폴백(현 동작).
    assert lookup_brand_awareness("코카콜라 신제품 광고") is None


def test_lookup_matches_brand_by_name_and_alias() -> None:
    hit = lookup_brand_awareness("신제품 더미브랜드 출시", data=_FIXTURE)
    assert hit and hit["awareness_brand"] == "더미브랜드"
    assert hit["awareness_by_age"]["20-29"] == 0.8
    assert hit["awareness_tier"] == 3
    # 영문 별칭(공백·대소문자 무시)도 매칭.
    assert lookup_brand_awareness("buy DummyBrand now", data=_FIXTURE) is not None


def test_awareness_band_mapping() -> None:
    assert _awareness_band(15) == "10-19"
    assert _awareness_band(25) == "20-29"
    assert _awareness_band(67) == "60-69"


def test_awareness_lines_render_and_fallback() -> None:
    # 부착 없으면 "" — 현 동작 보존.
    assert _awareness_lines(AdInterpretation(ad_id="A"), 25) == ""
    ad = AdInterpretation(
        ad_id="A",
        structured_analysis={
            "awareness_by_age": {"20-29": 0.8, "60-69": 0.2},
            "awareness_brand": "더미브랜드",
        },
    )
    # 내 연령대 칸을 읽어 줄 생성.
    line = _awareness_lines(ad, 25)
    assert "더미브랜드" in line and "80%" in line
    assert "20%" in _awareness_lines(ad, 67)
    # 내 연령대 칸 없으면 "".
    assert _awareness_lines(ad, 35) == ""


def test_data_status_brand_awareness_pending() -> None:
    assert "pending" in loader.data_status()["brand_awareness"]
