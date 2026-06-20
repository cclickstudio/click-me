from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
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

    # 어댑터 모드 — True면 Mock(데모·기본), False면 실연동 어댑터. wiring.py 분기 기준.
    use_mock: bool = True

    # Database
    database_url: str

    # OpenAI
    openai_api_key: str

    # Anthropic
    anthropic_api_key: str

    # Google Gemini
    gemini_api_key: str | None = None

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
    sqs_simulation_queue_url: str
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
    meta_graph_api_version: str = "v23.0"
    # 멀티테넌트 — 고객별 Meta 토큰 암호화 키(AES-256, base64 32B). 미설정이면 연결 저장 불가.
    meta_token_encryption_key: str | None = None
    # OAuth 콜백 완료 후 돌아갈 프론트 주소(개발=3000, 운영=https://clickme.co.kr).
    frontend_base_url: str = "http://localhost:3000"

    # Management — Meta 광고 어댑터 (LIVE-ready). use_mock은 App 섹션에서 공용 선언.
    # use_mock=True면 reader=Mock·writer=DRY_RUN (Meta 접촉 0, wiring.py 분기).
    # 실집행은 use_mock=False + management_execution_mode=live + 토큰일 때만.
    management_execution_mode: str = "dry_run"  # dry_run | validate_only | live

    # Generator (광고 생성)
    # 생성 방식: pipeline=카피·이미지 단계 분리 / multimodal=한 모델이 이미지+카피 동시 생성
    generator_gen_mode: str = "pipeline"  # pipeline | multimodal
    # 텍스트(상품분석·전략·카피·QA·설명)
    generator_text_provider: str = "openai"  # openai | anthropic | google_genai ...
    generator_text_model: str = "gpt-4.1"
    generator_text_base_url: str | None = None  # 회사 OpenAI-호환 엔드포인트용
    # 비전(이미지 분석)
    generator_vision_provider: str = "openai"  # openai | google_genai ...
    generator_vision_model: str = "gpt-4o"
    # 이미지 생성(배경)
    generator_image_provider: str = "openai"  # openai | google_genai
    generator_image_model: str = "gpt-image-2"
    generator_image_quality: str = "medium"  # openai 전용(low|medium|high), google_genai는 무시
    generator_image_timeout: float = 120.0  # 무거운 이미지 모델 대비 호출 타임아웃(초)
    # 이미지 편집(텍스트존 인페인팅)
    generator_image_edit_provider: str = "openai"  # openai
    generator_image_edit_model: str = "gpt-image-1"
    # 멀티모달 단일호출(이미지+카피) — GEN_MODE=multimodal 일 때만 사용
    generator_multimodal_provider: str = "openai"  # openai | google_genai
    generator_multimodal_model: str = "gpt-4o"  # Responses API 오케스트레이터(채팅 모델)
    generator_multimodal_image_model: str = "gpt-image-1"  # image_generation 툴이 그릴 이미지 모델
    generator_font_dir: str | None = None  # 없으면 backend/assets/fonts 사용

    # Toss Payments — 테스트 키 전용 (기본값 = 토스 공식 문서 공개 샌드박스 키)
    # 라이브 키 주입 시 기동 거부 — 실돈 결제는 7/8 Won't
    toss_client_key: str = "test_gck_docs_Ovk5rk1EwkEbP0W43n07xlzm"
    toss_secret_key: str = "test_gsk_docs_OaPz8L5KdmQXkzRz3y47BMw6"

    # JWT (Cognito 전환 전 임시)
    jwt_secret: str = "clickme-dev-secret-change-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7일

    @field_validator("toss_client_key", "toss_secret_key")
    @classmethod
    def _toss_keys_must_be_test(cls, value: str) -> str:
        return require_test_key(value)


settings = Settings()
