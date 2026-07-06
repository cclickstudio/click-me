# 시뮬레이터 도메인 DTO — 광고해석·페르소나·반응(§3.5)·루브릭·집계의 내부 계약
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from core.schemas import ScoreDistribution
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
# 분석 모드(§4-1 A-1 3-모드) — synthetic: 합성 표본(기본, 현행 동작) / individual: 단일 페르소나
# 심층(표본 1 강제) / persona_set: 세그먼트별 개별 실행 대조(POST /compare). target_mode(자동
# 타깃 추정 여부)와는 직교하는 개념이다.
AnalysisMode = Literal["synthetic", "individual", "persona_set"]


class SimulationRunRequest(BaseModel):
    """시뮬레이션 실행 입력 — 라우터 진입 DTO (도메인 내부 스키마)."""

    ad_id: str
    ad_content: str | None = None  # 실 광고 카피·설명(실 LLM 해석 입력). 없으면 mock/최소 해석.
    ad_image_url: str | None = None  # 광고 크리에이티브 이미지(URL·로컬경로) — VLM 해석 입력.
    ad_image_key: str | None = None  # S3 영구 식별자(업로드 시) — DB 영속·재조회 시 presign 대상.
    project_id: str | None = None
    organization_id: str | None = None
    # 사용자 식별(LangSmith 사용자별 필터용) — 라우터가 인증 사용자에서 채움(없으면 익명).
    user_id: str | None = None
    login_id: str | None = None
    user_name: str | None = None
    role: str | None = None
    target_filter: dict[str, Any] | None = None
    target_mode: TargetMode = TargetMode.AUTO
    sample_size: int = Field(default=20, ge=1, le=1000)
    allocation: AllocationChoice = "auto"  # auto면 sample_size로 자동 결정(아래 validator)
    # 3-모드 분석 — 기본 synthetic(현행 100% 유지). individual이면 sample_size=1 강제(validator).
    analysis_mode: AnalysisMode = "synthetic"
    # 선언 의도(광고 세부사항) — 의도 교차검증(§3.5-3) 비교 기준. 없으면 차원 스킵.
    ad_title: str | None = None  # 광고 제목 → message 차원(선언 핵심 메시지)
    product_category: str | None = None  # 제품 카테고리 → category 차원
    ad_objective: str | None = None  # 캠페인 목표 → objective 차원
    service_class: int | None = None  # 상품·서비스 분류(NICE 1~45) — 메타데이터(교차검증 차원 아님)
    # 성과 비교 자동 연결 — Meta 캠페인 ID(관리 탭에서 진입 시). 시뮬 저장 직후 서버가 직접 링크.
    from_campaign_id: str | None = None

    @model_validator(mode="after")
    def _resolve_allocation(self) -> SimulationRunRequest:
        # individual 모드는 단일 페르소나 심층 분석 → 표본 1 강제(배분 자동해석 전에 적용).
        if self.analysis_mode == "individual":
            self.sample_size = 1
        # auto면 표본 크기로 배분 결정 — 사용자 선택이 아니라 자동(§3.7). 300+ 대규모는 stratified로
        # 얇은 세그먼트(예 40대+ OCEAN)를 floor 보강해 세그먼트 신뢰도↑. 명시값은 그대로 존중.
        if self.allocation == "auto":
            self.allocation = (
                "stratified" if self.sample_size >= _AUTO_STRATIFIED_MIN else "proportional"
            )
        return self


class SegmentSpec(BaseModel):
    """persona_set 대조용 세그먼트 1개 — 라벨 + 타깃 필터 + 표본 크기(POST /compare 입력).

    target_filter는 {age_min, age_max, gender} — 기존 load_panel의 filter_personas가 소비한다.
    각 세그먼트는 별도 시뮬 런으로 개별 실행되어 SimRunResult로 대조된다.
    """

    label: str
    target_filter: dict[str, Any] | None = None
    sample_size: int = Field(default=20, ge=1, le=1000)


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
    """패널 빌드/조회 명세 — 고정 패널 운영(§3.6).

    캐시 로드는 CachedPanelProvider(tools/panel/builder.py)로 구현됨 — 런마다 재생성하지 않음.
    """

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
    social_economic: dict[str, float] = Field(
        default_factory=dict
    )  # 사회경제·심리 prior(MDIS 사회조사, 세대별 0~1) — 값 미확보 시 빈 dict(반응 무변화)
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
    # SSR 재배선(SIMULATION_SCORING=ssr, opt-in) — 서술 텍스트와 임베딩 기반 점수 분포.
    # 미사용(기본 llm) 시 전부 None — 기존 소비자(집계·토론·리포트) 무영향.
    reaction_text: dict[str, Any] | None = None  # LLM 자유 서술(SSR 입력) — 4-b 프롬프트 확장분
    purchase_intent_dist: ScoreDistribution | None = None  # SSR 분포(§KPI② 분포 표기 근거)
    trust_dist: ScoreDistribution | None = None  # SSR 분포(§KPI③)
    rejected: bool = False
    rejection_reason_tag: RejectionReasonTag | None = None
    emotion_tag: EmotionTag = EmotionTag.INDIFFERENCE
    perceived_message: str | None = None
    perceived_target: str | None = None
    # 브랜드 식별(Fluency, REPORT §2-5) — "어느 브랜드/제품 광고인지" 전달력. 사전 인지가 아님.
    brand_recognized: bool = False  # 명확히 식별했는가 — 가중 집계 입력(brand_recognition_rate)
    perceived_brand: str | None = None  # 인식한 브랜드/제품명(선언 의도와 대조해 오귀속 분해)
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

    ci_low/high 는 가중 부트스트랩(BasicAggregator._weighted_bootstrap_ci)으로,
    variance_warning 은 구매의도 가중표준편차 임계(_VARIANCE_MIN_STD)로 산출됨.
    """

    click_intent_rate: float
    ci_low: float
    ci_high: float
    purchase_intent: float
    trust_avg: float
    rejection_rate: float
    brand_recognition_rate: float = 0.0  # 브랜드 식별률(§2-5 Fluency) — QA 통과분 가중 비율
    variance_warning: bool = False
    effective_n: float = (
        0.0  # 유효표본수(Kish, §3.7) — 가중 편차 클수록 표본수보다 작아짐. CI 정직성
    )
    payload: dict[str, Any] = Field(default_factory=dict)
    engine_version: str = "agg-0"


class ObjectiveContribution(BaseModel):
    """목표 달성 가능성에 기여한 신호 1건 — 정규화값(0~1)과 가중치."""

    label: str  # 사람이 읽는 신호명("클릭 의향률" 등)
    value: float = Field(ge=0.0, le=1.0)  # 0~1 정규화 신호값
    weight: float = Field(ge=0.0, le=1.0)  # 이 목표에서의 가중치


class ObjectiveFit(BaseModel):
    """캠페인 목표 달성 가능성(결정론 룰) — 목표별 KPI 가중 조합의 상대 지표.

    실측 스케일 환산이 아니라 시뮬 신호 기반 '상대적 유리/불리' 지표다(exploratory).
    확률·실측 CTR로 단정하지 말 것 — 등급(grade)+상대점수(score)+근거(rationale)로만 표기.
    """

    objective: str  # 사용자 선언 캠페인 목표(원문)
    matched_goal: str  # 매핑된 목표 유형(awareness/click/lead/purchase/retention/general)
    score: int = Field(ge=0, le=100)  # 0~100 상대 지수(확률 아님)
    grade: str  # 높음 / 보통 / 낮음
    rationale: str  # 강점·약점 한 줄 근거
    contributions: list[ObjectiveContribution] = Field(default_factory=list)
    low_confidence: bool = False  # 유효표본 부족 등으로 신뢰 낮음
    exploratory: bool = True  # 항상 탐색적 — 실측 보정 전
