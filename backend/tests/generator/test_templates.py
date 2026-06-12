"""템플릿 정의 및 레이아웃 프롬프트 렌더러 테스트."""

from domain.generator.contracts.templates import (
    TEMPLATES,
    catalog_prompt,
    default_template_for,
    get_template,
    map_image_size,
)


def test_templates_are_a_b_c():
    assert set(TEMPLATES) == {"A", "B", "C"}


def test_template_a_layout_prompt_contains_areas_and_coords():
    prompt = get_template("A").layout_prompt()
    assert "Logo Area" in prompt
    assert "CTA Area" in prompt
    assert "가로 80~95%" in prompt  # Logo Area x 좌표 (계획서 16장)
    assert "세로 85~92%" in prompt  # CTA Area y 좌표


def test_catalog_prompt_mentions_all_templates():
    catalog = catalog_prompt()
    for template in TEMPLATES.values():
        assert f"[Template {template.template_id}]" in catalog
        assert template.name in catalog


def test_default_template_for_strategy():
    assert default_template_for("fomo").template_id == "B"
    assert default_template_for("social_proof").template_id == "C"
    assert default_template_for("unknown_type").template_id == "A"  # 폴백


def test_map_image_size():
    assert map_image_size(1080, 1080) == "1024x1024"
    assert map_image_size(1920, 1080) == "1536x1024"
    assert map_image_size(1080, 1920) == "1024x1536"
