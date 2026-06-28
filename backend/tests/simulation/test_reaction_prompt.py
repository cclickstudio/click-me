# 반응 프롬프트 강화 단위 테스트 — OCEAN 정성 묘사·미디어 이용강도·VLM 목적/피사체
from __future__ import annotations

from domain.simulation.adapters.gemini.reaction import (
    _generation_lines,
    _has_age_or_brand_cue,
    _media_line,
    _ocean_descriptors,
    _ocean_level,
    _trust_anchor_line,
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


def test_trust_anchor_has_scale() -> None:
    line = _trust_anchor_line()
    assert "1=" in line and "5=" in line  # 1·5점 앵커 명시
    assert "믿을 만하다" in line


def test_has_age_or_brand_cue() -> None:
    # brand_era.identified → True
    assert _has_age_or_brand_cue(
        AdInterpretation(ad_id="A", structured_analysis={"brand_era": {"identified": True}})
    )
    # 비어있지 않은 awareness_by_age → True
    assert _has_age_or_brand_cue(
        AdInterpretation(ad_id="A", structured_analysis={"awareness_by_age": {"20-29": 0.8}})
    )
    # 연령 특정 detected_target → True
    assert _has_age_or_brand_cue(AdInterpretation(ad_id="A", detected_target="20대"))
    # 포괄 타깃 → False
    assert not _has_age_or_brand_cue(AdInterpretation(ad_id="A", detected_target="전 연령"))
    # 빈 brand_era / 빈 awareness / 단서 없음 → False
    assert not _has_age_or_brand_cue(
        AdInterpretation(ad_id="A", structured_analysis={"brand_era": {"identified": False}})
    )
    assert not _has_age_or_brand_cue(AdInterpretation(ad_id="A"))


def test_generation_lines_gates_familiarity_frame() -> None:
    # 단서 없는 광고 — 세대 친숙도 프레임 부재, 말투 지침은 유지.
    bare = _generation_lines(45, AdInterpretation(ad_id="A"))
    assert "젊은 세대" not in bare
    assert "내 세대에 익숙한지" not in bare
    assert "말투" in bare
    # 단서 있는 광고(연령 특정 타깃) — 친숙도 프레임 존재 + 말투 유지.
    cued = _generation_lines(45, AdInterpretation(ad_id="A", detected_target="20대"))
    assert "젊은 세대" in cued
    assert "말투" in cued
