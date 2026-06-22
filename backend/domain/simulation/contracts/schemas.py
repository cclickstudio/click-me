# 시뮬레이터 도메인 DTO — 광고해석·페르소나·반응(§3.5)·루브릭·집계의 내부 계약
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from domain.simulation.contracts.enums import (
    DropReasonTag,
    EmotionTag,
    RejectionReasonTag,
    TargetMode,
)

# 표본 배분 방식(§3.7) — proportional: 인구비례 self-weighting / stratified: 층화 과대표집+가중보정
Allocation = Literal["proportional", "stratified"]
# 요청 배분 선택지 — auto(기본)면 sample_size로 자동 결정(사용자 선택 아님, §3.5).
AllocationChoice = Literal["auto", "proportional", "stratified"]
# auto 임계 — 이상이면 stratified(얇은 층 floor 보강), 미만이면 proportional.
_AUTO_STRATIFIED_MIN = 300


class SimulationRunRequest(BaseModel):
    """시뮬레이션 실행 입력 — 라우터 진입 DTO (도메인 내부 스키마)."""

    ad_id: str
    ad_content: str | None = None  # 실 광고 카피·설명(실 LLM 해석 입력). 없으면 mock/최소 해석.
    ad_image_url: str | None = None  # 광고 크리에이티브 이미지(URL·로컬경로) — VLM 해석 입력.
    project_id: str | None = None
    organization_id: str | None = None
    target_filter: dict[str, Any] | None = None
    target_mode: TargetMode = TargetMode.AUTO
    sample_size: int = Field(default=20, ge=1, le=1000)
    allocation: AllocationChoice = "auto"  # auto면 sample_size로 자동 결정(아래 validator)
    # 선언 의도(광고 세부사항) — 의도 교차검증(§3.5-3) 비교 기준. 없으면 차원 스킵.
    ad_title: str | None = None  # 광고 제목 → message 차원(선언 핵심 메시지)
    product_category: str | None = None  # 제품 카테고리 → category 차원
    ad_objective: str | None = None  # 캠페인 목표 → objective 차원
    service_class: int | None = None  # 상품·서비스 분류(NICE 1~45) — 메타데이터(교차검증 차원 아님)

    @model_validator(mode="after")
    def _resolve_allocation(self) -> SimulationRunRequest:
        # auto면 표본 크기로 배분 결정 — 사용자 선택이 아니라 자동(§3.7). 300+ 대규모는 stratified로
        # 얇은 세그먼트(예 40대+ OCEAN)를 floor 보강해 세그먼트 신뢰도↑. 명시값은 그대로 존중.
        if self.allocation == "auto":
            self.allocation = (
                "stratified" if self.sample_size >= _AUTO_STRATIFIED_MIN else "proportional"
            )
        return self


class AdFeatures(BaseModel):
    """광고 특성 정량 추출 — 반응 프롬프트 입력 힌트(KPI 환산 금지). 전 필드 옵셔널(하위호환).

    DB 컬럼 아님 — AdInterpretation.structured_analysis(JSONB)에 함께 담겨 영속된다.
    """

    ad_credibility: int | None = None  # 증거·현실성·정직성 종합(0~100, LLM 추정)
    ad_quality: int | None = None  # 명확성·매력·구조·CTA 종합(0~100)
    price_mentioned: bool = False
    original_price: int | None = None
    discounted_price: int | None = None
    brand_mentioned: bool = False
    social_proof_strength: Literal["high", "medium", "low", "none"] | None = None


class AdInterpretation(BaseModel):
    """광고해석 — vision 구조화 산출 (exposure·페르소나 생성의 입력)."""

    ad_id: str
    structured_analysis: dict[str, Any] = Field(default_factory=dict)
    detected_industry: str | None = None
    detected_objective: str | None = None  # 감지 캠페인 목표 — objective 차원 교차검증용
    detected_target: str | None = None
    detected_message: str | None = None
    ad_features: AdFeatures = Field(default_factory=AdFeatures)  # 정량 광고 특성(반응 힌트)
    intent_mismatch: bool = False
    mismatch_detail: dict[str, Any] | None = None
    model_version: str = "mock-0"


class PanelSpec(BaseModel):
    """패널 빌드/조회 명세 — 고정 패널 운영(§3.6). 캐시는 추후 구현."""

    version: str = "panel-v1"
    size: int = Field(default=20, ge=1, le=1000)
    seed: int = 0
    target_filter: dict[str, Any] | None = None
    allocation: Allocation = "proportional"


class Persona(BaseModel):
    """패널 멤버 프로필 — 반응은 캐시하지 않고 광고마다 새로 생성."""

    persona_id: str
    age: int
    gender: str
    region: str
    ocean: dict[str, float]
    media_behavior: dict[str, Any] = Field(default_factory=dict)
    consumption_values: dict[str, Any] = Field(default_factory=dict)
    socioeconomic: dict[str, Any] = Field(
        default_factory=dict
    )  # 소득·학력(KISDI, 구매의도 grounding)
    social_values_deep: dict[str, float] = Field(
        default_factory=dict
    )  # 단계3 한국 특화 심리(체면·동조·눈치) — 값 미확보 시 빈 dict(반응 무변화)
    weight: float = Field(
        default=1.0, gt=0
    )  # 표본 가중치(§3.7) — 비례추출 기본 1.0(self-weighting)
    profile_narrative: str = ""


class Aisas(BaseModel):
    attention: bool = False
    interest: bool = False
    search: bool = False
    action: bool = False
    share: bool = False


class PersonaReaction(BaseModel):
    """4-b 반응 산출 — 팀 간 인터페이스 계약(PERSONA §3.5). 분석팀 입력."""

    persona_id: str
    exposure_context: str | None = None
    weight: float = Field(default=1.0, gt=0)  # 페르소나 가중치 사본(§3.7) — 가중 집계 입력
    aisas: Aisas
    drop_stage: str | None = None
    drop_reason_tag: DropReasonTag | None = None
    purchase_intent: int = Field(ge=1, le=5)
    trust: int = Field(ge=1, le=5)
    rejected: bool = False
    rejection_reason_tag: RejectionReasonTag | None = None
    emotion_tag: EmotionTag = EmotionTag.INDIFFERENCE
    perceived_message: str | None = None
    perceived_target: str | None = None
    noticed_first: str | None = None  # §4-b salience — 프로필상 가장 먼저 주의가 간 요소(탐색적)
    utterance: str | None = None
    qa_passed: bool = True
    qa_fail_reason: str | None = None


class RubricScore(BaseModel):
    """루브릭 평가 패스(숫자) — §4 진단 입력. 문장 생성은 분석팀."""

    dimension: str
    score: int = Field(ge=0, le=100)
    evidence: dict[str, Any] = Field(default_factory=dict)


class SimulationAggregate(BaseModel):
    """집계 엔진 산출 — 분석팀·리포트 입력 계약.

    ci_low/high·variance_warning 의 정식 산출(부트스트랩 등)은 추후 구현.
    """

    click_intent_rate: float
    ci_low: float
    ci_high: float
    purchase_intent: float
    trust_avg: float
    rejection_rate: float
    variance_warning: bool = False
    effective_n: float = (
        0.0  # 유효표본수(Kish, §3.7) — 가중 편차 클수록 표본수보다 작아짐. CI 정직성
    )
    payload: dict[str, Any] = Field(default_factory=dict)
    engine_version: str = "agg-0"
