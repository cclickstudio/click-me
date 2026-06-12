"""Generator DTO — 요청/응답/내부 산출물 스키마."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerationCreateRequest(BaseModel):
    """생성모드 입력 (계획서 5장)."""

    project_id: str | None = None
    product_name: str
    product_description: str
    target_audience: str
    campaign_objective: str = "conversion"
    brand_color: str | None = None  # hex (#RRGGBB)
    brand_logo_url: str | None = None
    tone_and_manner: str | None = None
    width: int = Field(default=1080, ge=256, le=4096)
    height: int = Field(default=1080, ge=256, le=4096)


class ProductAnalysis(BaseModel):
    """상품 분석 결과 — 핵심가치 / Pain Point / Benefit."""

    core_values: list[str]
    pain_points: list[str]
    benefits: list[str]


class AdStrategy(BaseModel):
    """광고 전략 (후보 1종당 1개, 서로 다른 방향)."""

    strategy_type: str  # benefit | fomo | social_proof | emotional | problem_solution
    name: str  # 한국어 전략명 (예: 혜택 강조)
    key_message: str
    rationale: str


class StrategySet(BaseModel):
    strategies: list[AdStrategy]


class TemplateAssignment(BaseModel):
    """전략 → 템플릿 매핑 (AI 자동 선택)."""

    strategy_type: str
    template_id: str  # A | B | C
    reason: str


class TemplateAssignmentSet(BaseModel):
    assignments: list[TemplateAssignment]


class AdCopy(BaseModel):
    """광고 카피 — 템플릿 영역별 문구."""

    headline: str
    subcopy: str
    benefit_text: str
    cta: str


class QACheck(BaseModel):
    name: str
    passed: bool
    detail: str


class QAResult(BaseModel):
    """QA Harness 결과 — 7항목 (계획서 8장)."""

    checks: list[QACheck]
    passed: bool


class LLMQAVerdict(BaseModel):
    passed: bool
    detail: str


class LLMQAResult(BaseModel):
    """LLM이 판단하는 QA 4항목 (오타 / 가독성 / 타겟 적합성 / 브랜드 일관성)."""

    typo: LLMQAVerdict
    readability: LLMQAVerdict
    target_fit: LLMQAVerdict
    brand_consistency: LLMQAVerdict


class CandidateExplanation(BaseModel):
    """생성 이유 설명 (계획서 8장)."""

    applied_target: str
    applied_strategy: str
    applied_template: str
    rationale: str
