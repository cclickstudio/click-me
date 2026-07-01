from pathlib import Path

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from domain.billing.toss_client import require_test_key

BACKEND_ROOT = Path(__file__).resolve().parent.parent
# .env 는 프로젝트 루트 우선(현 배치), 없으면 backend/.env 폴백.
_ROOT_ENV = BACKEND_ROOT.parent / ".env"
ENV_FILE = _ROOT_ENV if _ROOT_ENV.exists() else BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    internal_api_base_url: str = "http://localhost:8000"
    # CORS 추가 허용 origin(콤마 구분). 운영 배포 주소 등. 예: http://1.2.3.4:3000
    cors_allow_origins: str = ""

    # 어댑터 모드 — True면 Mock(데모·기본), False면 실연동 어댑터. wiring.py 분기 기준.
    use_mock: bool = True
    # 핸드오프/수동 캠페인 생성 시 광고(소재) 단계 생성 여부.
    # False(기본): 캠페인+광고세트까지만(Meta access level 전 1885183 회피).
    # True: 광고까지 풀 생성(Marketing API Access Tier/Advanced 확보 후).
    management_create_ad: bool = False

    # Database
    database_url: str

    # OpenAI
    openai_api_key: str

    # Anthropic
    anthropic_api_key: str

    # Google Gemini
    gemini_api_key: str | None = None

    # Tavily 웹검색(매니지먼트 어시스턴트 web_search 도구) — 없으면 웹검색 graceful 비활성
    tavily_api_key: str | None = None

    # LangSmith — API 키 없으면 트레이싱 비활성(로컬 기동 가능)
    # LANGCHAIN_* 사용, LANGSMITH_*도 AliasChoices로 수용.
    LANGSMITH_TRACING_V2: bool = Field(
        default=True,
        validation_alias=AliasChoices("LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING_V2"),
    )
    LANGSMITH_ENDPOINT: str = Field(
        default="https://api.smith.langchain.com",
        validation_alias=AliasChoices("LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT"),
    )
    LANGSMITH_API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
    )
    LANGSMITH_PROJECT: str = Field(
        default="clickme",
        validation_alias=AliasChoices("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT"),
    )

    # AWS
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "ap-northeast-2"
    s3_bucket_name: str = "clickme-assets"
    sqs_simulation_queue_url: str | None = None
    sqs_max_workers: int = 10

    # Simulation
    default_persona_count: int = Field(default=20, ge=1, le=1000)
    max_persona_count: int = Field(default=1000, ge=1)

    # Meta / Instagram (Generator) — 비우면 Mock 게시 모드
    # App
    meta_app_id: str | None = None
    meta_app_secret: str | None = None
    meta_business_id: str | None = None  # 비즈니스 포트폴리오 ID
    # User
    meta_access_token: str | None = None
    meta_user_id: str | None = None
    # Facebook Page
    meta_page_id: str | None = None
    meta_page_access_token: str | None = None
    # Instagram (META_IG_USER_ID → META_INSTAGRAM_ACCOUNT_ID, 구형 이름도 수용)
    meta_instagram_account_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("META_INSTAGRAM_ACCOUNT_ID", "META_IG_USER_ID"),
    )
    # Marketing (Phase 6 광고 집행용)
    meta_ad_account_id: str | None = None
    # Config
    meta_graph_api_version: str = "v21.0"
    # 멀티테넌트 — 고객별 Meta 토큰 암호화 키(AES-256, base64 32B). 미설정이면 연결 저장 불가.
    meta_token_encryption_key: str | None = None
    # OAuth 콜백 완료 후 돌아갈 프론트 주소(개발=3000, 운영=https://clickme.co.kr).
    frontend_base_url: str = "http://localhost:3000"
    # 내부 서비스 호출 토큰 — 매니지먼트→제너레이터(from-candidate) 같은 무인증 내부 HTTP 호출용.
    # 설정 시 generator 조회가 org 스코프되며 이 헤더만 우회 허용. 미설정(dev)이면 우회 검사 생략.
    internal_service_token: str | None = None

    # Management — Meta 광고 어댑터 (LIVE-ready). use_mock은 App 섹션에서 공용 선언.
    # use_mock=True면 reader=Mock·writer=DRY_RUN (Meta 접촉 0, wiring.py 분기).
    # 실집행은 use_mock=False + management_execution_mode=live + 토큰일 때만.
    management_execution_mode: str = "dry_run"  # dry_run | validate_only | live
    # 능동 스케줄러(주기 이상 스캔→알림) — 기본 off(테스트/CI/dev 안전). 운영에서만 켠다.
    management_scheduler_enabled: bool = False
    management_scan_interval_minutes: int = 60
    # 진단 agent LLM ReAct 재현성 고정값 (합의문서 P6 — 빈칸 기입). 키 없으면 결정론 폴백.
    management_diagnosis_model: str = "gpt-4o-mini"
    management_diagnosis_temperature: float = 0.0
    # 어시스턴트 ReAct 그래프 LLM 모델 — MANAGEMENT_ASSISTANT_MODEL 환경변수로 오버라이드 가능.
    management_assistant_model: str = "gpt-4o-mini"

    # Embedding (KB·LTM 공유 — 동일 모델·차원 필수. spec §6.1/§9)
    # provider=bge_m3(기본): TEI/Ollama 로컬 서빙 1024차원.
    # provider=openai: 1536(별도 마이그레이션 필요).
    # USE_MOCK 또는 키 부재 시 wiring이 MockEmbeddingProvider(embedding_dim 차원) 반환.
    embedding_provider: str = "bge_m3"  # bge_m3 | openai | mock
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embedding_base_url: str = "http://localhost:8080"  # TEI /embed 엔드포인트
    openai_embedding_model: str = "text-embedding-3-small"  # provider=openai 폴백(1536)

    # Chat orchestrator (Phase ③-B에서 사용 — 기반 단계는 설정만 선반영)
    chat_orchestrator_provider: str = "openai"  # anthropic | openai | google_genai
    chat_orchestrator_model: str = "gpt-4.1"  # 챗 답변 엔진. 임베딩·검색은 OpenAI
    chat_classify_model: str = "gpt-4.1"  # 분류·슬롯 추출 경량 모델(답변과 분리, 지연↓)
    chat_orchestrator_temperature: float = 0.3

    # Generator (광고 생성)
    # 생성 방식: openai=OpenAI 이미지(상품있음 누끼·인페인팅 / 없음 0부터)
    #            gemini=Gemini 멀티모달(이미지+카피 동시 생성)
    generator_gen_mode: str = "openai"  # openai | gemini
    # 텍스트(상품분석·전략·카피·QA·설명)
    generator_text_provider: str = "openai"  # openai | anthropic | google_genai ...
    generator_text_model: str = "gpt-4.1"
    generator_text_base_url: str | None = None  # 회사 OpenAI-호환 엔드포인트용
    # 비전(이미지 분석)
    generator_vision_provider: str = "openai"  # openai | google_genai ...
    generator_vision_model: str = "gpt-4o"
    # 이미지 생성(배경)
    generator_image_provider: str = "openai"  # openai | google_genai
    generator_image_model: str = "gpt-image-1"
    generator_image_quality: str = "medium"  # openai 전용(low|medium|high), google_genai는 무시
    generator_image_timeout: float = 120.0  # 무거운 이미지 모델 대비 호출 타임아웃(초)
    # 이미지 편집(누끼 배경제거 — remove_product_background)
    generator_image_edit_provider: str = "openai"  # openai
    generator_image_edit_model: str = "gpt-image-1"
    # 이미지 생성(gemini 모드) — GEN_MODE=gemini 일 때 사용.
    # native 모델이 이미지+카피를 한 호출로 출력. gemini-3-pro-image 등으로 교체 가능.
    generator_gemini_image_model: str = "gemini-2.5-flash-image"
    # ── 작업별 이미지 모델 오버라이드 (operation 단위 스위칭) ──
    # 미설정(None)이면 위 기존 설정으로 폴백 → 기본 동작 불변. 해석은 cutout_*/inpaint_* 프로퍼티.
    generator_cutout_provider: str | None = None  # 누끼 — 폴백: image_edit_provider
    generator_cutout_model: str | None = None  # 누끼 — 폴백: image_edit_model
    generator_cutout_quality: str | None = None  # 누끼 — 폴백: image_quality
    generator_inpaint_provider: str | None = None  # 인페인팅 — 폴백: image_provider
    generator_inpaint_model: str | None = None  # 인페인팅 — 폴백: image_model
    generator_font_dir: str | None = None  # 없으면 backend/assets/fonts 사용

    # Toss Payments — 테스트 키 전용 (기본값 = 토스 공식 문서 공개 샌드박스 키)
    # 라이브 키 주입 시 기동 거부 — 실돈 결제는 7/8 Won't
    toss_client_key: str = "test_gck_docs_Ovk5rk1EwkEbP0W43n07xlzm"
    toss_secret_key: str = "test_gsk_docs_OaPz8L5KdmQXkzRz3y47BMw6"

    # JWT (auth_provider=local 일 때 — 자체 HS256 발급/검증)
    jwt_secret: str = "clickme-dev-secret-change-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7일

    # ── Auth provider (점진 도입) ──────────────────────────────
    # "local"(기본): 자체 HS256 JWT. "cognito": AWS Cognito User Pool 토큰(JWKS·RS256) 검증.
    # 기본이 local이라 Cognito 미설정 시 기존 인증이 그대로 동작한다.
    auth_provider: str = "local"  # local | cognito
    # Cognito (auth_provider=cognito 일 때만 사용). User Pool은 콘솔에서 생성하고 값은 .env로 주입.
    # 매핑 규약: Cognito username = 우리 User.login_id (스키마 변경 없이 sub↔User 해결).
    cognito_region: str | None = None  # 미설정 시 aws_region 사용
    cognito_user_pool_id: str | None = None  # 예: ap-northeast-2_xxxxxxxxx
    cognito_app_client_id: str | None = None  # ID 토큰 audience(aud) 검증값

    @field_validator("toss_client_key", "toss_secret_key")
    @classmethod
    def _toss_keys_must_be_test(cls, value: str) -> str:
        return require_test_key(value)

    @model_validator(mode="after")
    def _check_cognito_config(self) -> "Settings":
        # cognito 모드를 켰는데 필수 값이 비면 기동 시점에 명확히 실패(런타임 401 디버깅 방지).
        if self.auth_provider == "cognito" and not (
            self.cognito_user_pool_id and self.cognito_app_client_id
        ):
            raise ValueError(
                "AUTH_PROVIDER=cognito 면 COGNITO_USER_POOL_ID·COGNITO_APP_CLIENT_ID 가 필요합니다."
            )
        return self

    # ── Cognito 파생값 (region + pool_id 로 구성) ──
    @property
    def cognito_issuer(self) -> str:
        region = self.cognito_region or self.aws_region
        return f"https://cognito-idp.{region}.amazonaws.com/{self.cognito_user_pool_id}"

    @property
    def cognito_jwks_uri(self) -> str:
        return f"{self.cognito_issuer}/.well-known/jwks.json"

    # ── 작업별 이미지 설정 해석 (오버라이드 없으면 기존 설정으로 폴백) ──
    @property
    def cutout_provider(self) -> str:
        return self.generator_cutout_provider or self.generator_image_edit_provider

    @property
    def cutout_model(self) -> str:
        return self.generator_cutout_model or self.generator_image_edit_model

    @property
    def cutout_quality(self) -> str:
        return self.generator_cutout_quality or self.generator_image_quality

    @property
    def inpaint_provider(self) -> str:
        return self.generator_inpaint_provider or self.generator_image_provider

    @property
    def inpaint_model(self) -> str:
        return self.generator_inpaint_model or self.generator_image_model


settings = Settings()
