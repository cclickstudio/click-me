# 반응 프롬프트 강화 단위 테스트 — OCEAN 정성 묘사·미디어 이용강도·VLM 목적/피사체
from __future__ import annotations

from domain.simulation.adapters.gemini.reaction import (
    _media_line,
    _ocean_descriptors,
    _ocean_level,
    _visual_lines,
)
from domain.simulation.contracts.schemas import AdInterpretation


def test_ocean_level_bands() -> None:
    assert _ocean_level(1.4) == "매우 높음"
    assert _ocean_level(0.5) == "높음"
    assert _ocean_level(0.0) == "보통"
    assert _ocean_level(-0.6) == "낮음"
    assert _ocean_level(-1.2) == "매우 낮음"


def test_ocean_descriptors_readable() -> None:
    d = _ocean_descriptors(
        {
            "openness": 1.2,
            "conscientiousness": 0.0,
            "extraversion": -1.1,
            "agreeableness": 0.5,
            "neuroticism": -0.6,
        }
    )
    assert "개방성 매우 높음" in d and "외향성 매우 낮음" in d
    assert _ocean_descriptors({}) == "(미상)"  # 빈 OCEAN 안전


def test_media_line_intensity() -> None:
    assert "헤비 이용자" in _media_line({"primary_medium": "스마트폰", "daily_media_minutes": 400})
    assert "라이트 이용자" in _media_line({"primary_medium": "TV", "daily_media_minutes": 60})
    # 분 정보 없으면 매체만(현 동작).
    assert _media_line({"primary_medium": "PC"}) == "- 주 이용 미디어: PC"


def test_visual_lines_includes_primary_subject() -> None:
    ad = AdInterpretation(
        ad_id="A",
        structured_analysis={
            "visual_elements": {"primary_subject": "제품 캔", "first_impression": "파란 캔"}
        },
    )
    assert "핵심 피사체: 제품 캔" in _visual_lines(ad)
    # visual_elements 없으면 ""(현 동작).
    assert _visual_lines(AdInterpretation(ad_id="A")) == ""
