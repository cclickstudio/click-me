from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OCEAN(BaseModel):
    openness: float = Field(ge=0.0, le=1.0)
    conscientiousness: float = Field(ge=0.0, le=1.0)
    extraversion: float = Field(ge=0.0, le=1.0)
    agreeableness: float = Field(ge=0.0, le=1.0)
    neuroticism: float = Field(ge=0.0, le=1.0)


class PersonaAttributes(BaseModel):
    age: int
    gender: str
    region: str
    occupation: str
    income_level: str
    education: str
    purchase_motivation: str
    price_sensitivity: float = Field(ge=0.0, le=1.0)
    brand_loyalty: float = Field(ge=0.0, le=1.0)
    impulse_buying_tendency: float = Field(ge=0.0, le=1.0, default=0.5)
    core_values: list[str] = Field(default_factory=list)
    consumption_style: str | None = None
    recent_purchase_experience: str | None = None
    current_concern: str | None = None
    trigger_words: list[str] = Field(default_factory=list)
    rejection_words: list[str] = Field(default_factory=list)
    current_emotion: str | None = None


class Persona(BaseModel):
    persona_id: str
    segment: str
    ocean: OCEAN
    attributes: PersonaAttributes
    temperature: float = 0.7
    seed: int = 0


class ScoreDistribution(BaseModel):
    mean: float
    std: float
    p10: float
    p90: float
    raw_probs: list[float]


class ReactionSignals(BaseModel):
    attention: ScoreDistribution
    sentiment: ScoreDistribution
    click_intent: ScoreDistribution
    conversion_intent: ScoreDistribution
    comprehension: ScoreDistribution
    recall: ScoreDistribution


class PersonaReaction(BaseModel):
    schema_version: str = "2.0"
    simulation_id: str
    producer_id: str
    persona_id: str
    segment: str
    free_text_reaction: str
    exposure_output: dict[str, Any]
    deliberation_output: dict[str, Any]
    signals: ReactionSignals
    confidence: float | None = None


class AggregateResult(BaseModel):
    schema_version: str = "2.0"
    simulation_id: str
    sample_size: int
    aggregate_purchase_intent: list[float]
    kobaco_comparable: bool
    signal_distributions: dict[str, ScoreDistribution]
    kpi: dict[str, float]
    funnel: dict[str, float]
    effectiveness_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class AdTextContent(BaseModel):
    headline: str
    body: str
    cta: str


class TextAnalysis(BaseModel):
    headline: str | None = None
    sub_headline: str | None = None
    body: str | None = None
    cta: str | None = None
    usp_extracted: list[str] = Field(default_factory=list)
    emotional_keywords: list[str] = Field(default_factory=list)


class VisualAnalysis(BaseModel):
    dominant_colors: list[str] = Field(default_factory=list)
    emotional_tone: str | None = None
    layout_type: str | None = None
    brand_elements: list[str] = Field(default_factory=list)


class StrategicAnalysis(BaseModel):
    target_demographic: str | None = None
    purchase_stage_target: str = "conversion"
    usp: str | None = None
    key_message: str | None = None
    likely_resonates_with: list[str] = Field(default_factory=list)
    likely_resists_with: list[str] = Field(default_factory=list)
    potential_objections: list[str] = Field(default_factory=list)


class AdAnalysisResult(BaseModel):
    ad_id: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    text_analysis: TextAnalysis
    visual_analysis: VisualAnalysis | None = None
    strategic_analysis: StrategicAnalysis


class SimulationRequest(BaseModel):
    simulation_id: str
    ad_analysis: dict[str, Any]
    personas: list[dict[str, Any]] = Field(default_factory=list)
    objective: str = "conversion"
    persona_set: dict[str, Any] = Field(default_factory=dict)


class SimulationTaskResponse(BaseModel):
    task_id: str
    stream_url: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    messages: list[ChatMessage]
    context_ad_id: str | None = None
    context_simulation_id: str | None = None


class InquiryCreate(BaseModel):
    title: str = Field(max_length=300)
    content: str
    contact_email: str | None = None


class UserCreate(BaseModel):
    email: str
    name: str
    role: str = "user"
    initial_password: str


class ProjectCreate(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = None
