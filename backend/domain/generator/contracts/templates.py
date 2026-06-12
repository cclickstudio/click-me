"""광고 템플릿 정의 — 전략 + 레이아웃을 함께 정의 (계획서 14~18장).

공통 규격: 1080x1080 (Instagram Feed), Safe Area 5%, Content Area 5~95%.
"""

from __future__ import annotations

from pydantic import BaseModel


class TemplateArea(BaseModel):
    name: str
    x: tuple[int, int]  # 가로 % 범위
    y: tuple[int, int]  # 세로 % 범위


class AdTemplate(BaseModel):
    template_id: str
    name: str
    strategies: list[str]  # 적합한 strategy_type 목록
    description: str
    areas: list[TemplateArea]

    def layout_prompt(self) -> str:
        """% 좌표를 이미지 프롬프트용 자연어 레이아웃 지시문으로 렌더링."""
        return "\n".join(
            f"- {a.name}: 가로 {a.x[0]}~{a.x[1]}%, 세로 {a.y[0]}~{a.y[1]}% 위치" for a in self.areas
        )


TEMPLATES: dict[str, AdTemplate] = {
    "A": AdTemplate(
        template_id="A",
        name="제품 강조형",
        strategies=["benefit", "problem_solution"],
        description="제품 비주얼을 중앙에 크게 배치하고 혜택을 직관적으로 전달",
        areas=[
            TemplateArea(name="Logo Area", x=(80, 95), y=(5, 15)),
            TemplateArea(name="Headline Area", x=(10, 90), y=(10, 20)),
            TemplateArea(name="Product Area", x=(15, 85), y=(25, 70)),
            TemplateArea(name="Benefit Area", x=(10, 90), y=(72, 82)),
            TemplateArea(name="CTA Area", x=(20, 80), y=(85, 92)),
        ],
    ),
    "B": AdTemplate(
        template_id="B",
        name="이벤트 강조형",
        strategies=["fomo", "benefit"],
        description="프로모션·긴급성을 상단에 크게 배치해 즉각적인 행동 유도",
        areas=[
            TemplateArea(name="Logo Area", x=(80, 95), y=(5, 15)),
            TemplateArea(name="Promotion Area", x=(10, 90), y=(10, 30)),
            TemplateArea(name="Product Area", x=(20, 80), y=(35, 65)),
            TemplateArea(name="Event Detail Area", x=(10, 90), y=(68, 78)),
            TemplateArea(name="CTA Area", x=(15, 85), y=(82, 92)),
        ],
    ),
    "C": AdTemplate(
        template_id="C",
        name="브랜드 강조형",
        strategies=["social_proof", "emotional"],
        description="브랜드 메시지와 신뢰 요소를 중심으로 감성적인 톤 전달",
        areas=[
            TemplateArea(name="Logo Area", x=(25, 75), y=(10, 25)),
            TemplateArea(name="Brand Message Area", x=(10, 90), y=(30, 55)),
            TemplateArea(name="Product Area", x=(25, 75), y=(55, 75)),
            TemplateArea(name="Supporting Copy Area", x=(10, 90), y=(75, 85)),
            TemplateArea(name="CTA Area", x=(20, 80), y=(88, 95)),
        ],
    ),
}


def get_template(template_id: str) -> AdTemplate:
    return TEMPLATES[template_id]


def default_template_for(strategy_type: str) -> AdTemplate:
    """LLM 매핑 실패 시 전략에 맞는 기본 템플릿 (안전장치)."""
    for template in TEMPLATES.values():
        if strategy_type in template.strategies:
            return template
    return TEMPLATES["A"]


def catalog_prompt() -> str:
    """템플릿 선택 노드 프롬프트용 카탈로그 요약."""
    return "\n\n".join(
        f"[Template {t.template_id}] {t.name}\n"
        f"  적합 전략: {', '.join(t.strategies)}\n"
        f"  설명: {t.description}\n"
        f"  레이아웃:\n{t.layout_prompt()}"
        for t in TEMPLATES.values()
    )


def map_image_size(width: int, height: int) -> str:
    """요청 사이즈를 gpt-image-1 지원 사이즈로 매핑.

    gpt-image-1은 1024x1024 / 1536x1024 / 1024x1536만 지원한다.
    """
    if width == height:
        return "1024x1024"
    return "1536x1024" if width > height else "1024x1536"
