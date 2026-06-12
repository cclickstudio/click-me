from __future__ import annotations

from pydantic import BaseModel, Field

from domain.generator.contracts.enums import AdSize, AdStrategy, GenerationMode, TemplateType


# ── 요청 스키마 ──────────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    """생성모드 입력."""

    product_name: str
    description: str
    target: str
    objective: str  # awareness | conversion | lead_gen | promotion 등
    brand_color: str | None = None  # 예: "#FF5733"
    tone: str | None = None  # 예: "친근하고 활기찬"
    size: AdSize = AdSize.SQUARE


class ImproveRequest(BaseModel):
    """개선모드 입력."""

    existing_ad_s3_key: str
    simulation_summary: str  # 시뮬레이션 결과 핵심 내용
    fix_requests: str | None = None  # 추가 수정 요청사항
    brand_color: str | None = None
    tone: str | None = None
    size: AdSize = AdSize.SQUARE


# ── 파이프라인 내부 데이터 ─────────────────────────────────────────────────────


class ProductAnalysis(BaseModel):
    """product_analyzer 출력."""

    product_name: str
    core_values: list[str]
    pain_points: list[str]
    benefits: list[str]
    target_audience: str
    objective: str


class StrategyOutput(BaseModel):
    """strategy_planner 출력 (템플릿 결정 전)."""

    strategy: AdStrategy
    strategy_description: str
    headline: str
    body: str
    cta: str
    rationale: str


class AdCopy(BaseModel):
    headline: str
    body: str
    cta: str


class StrategyPlan(BaseModel):
    """template_selector 통과 후 확정된 전략."""

    strategy: AdStrategy
    strategy_description: str
    template: TemplateType
    ad_copy: AdCopy
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
    overall_passed: bool


# ── 응답 스키마 ───────────────────────────────────────────────────────────────


class GeneratedAdVariant(BaseModel):
    """생성된 광고 1종."""

    variant_id: str  # "A" | "B"
    strategy: AdStrategy
    template: TemplateType
    image_s3_key: str
    image_url: str  # presigned URL (24h)
    headline: str
    body: str
    cta: str
    rationale: str
    quality_report: QualityReport


class GenerateResult(BaseModel):
    generation_id: str
    mode: GenerationMode
    variants: list[GeneratedAdVariant]  # 항상 2종
    created_at: str
