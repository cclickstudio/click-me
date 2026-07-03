"""Generator 파이프라인 내부 산출물 DTO.

graph candidate 노드가 호출하는 pipeline/* 모듈들의 입출력 타입.
요청/응답(API) 스키마는 schemas.py(GenerationCreateRequest)와 service/get_detail 응답을 사용한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.generator.contracts.enums import AdStrategy, TemplateType


class ProductAnalysis(BaseModel):
    """product_analyzer 출력."""

    product_name: str
    core_values: list[str]
    pain_points: list[str]
    benefits: list[str]
    target_audience: str
    objective: str


class StrategyOutput(BaseModel):
    """strategy_planner 출력 (템플릿·copy 결정 전)."""

    strategy: AdStrategy
    strategy_description: str
    rationale: str


class AdCopy(BaseModel):
    headline: str
    body: str
    cta: str


class ImageAnalysis(BaseModel):
    """image_analyzer 출력."""

    dominant_colors: list[str]
    brightness: str  # "dark" | "medium" | "light"
    mood: str
    composition: str
    clear_zones: str
    suggested_text_color: str


class StrategyPlan(BaseModel):
    """template_selector 통과 후 확정된 전략 (copy 생성 전).

    개선 모드에서는 template=None — 자유 레이아웃(safe zone·템플릿 선택 없음).
    """

    strategy: AdStrategy
    strategy_description: str
    template: TemplateType | None = None
    rationale: str


# ── 품질 검증 ─────────────────────────────────────────────────────────────────


class QualityCheckItem(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    feedback: str


class QualityReport(BaseModel):
    typo_check: QualityCheckItem
    duplicate_check: QualityCheckItem
    cta_exists: QualityCheckItem
    readability: QualityCheckItem
    target_fit: QualityCheckItem
    text_length: QualityCheckItem
    brand_consistency: QualityCheckItem
    overall_passed: bool
    policy_warnings: list[str] = []
