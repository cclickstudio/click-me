from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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
        default="clickme-v2",
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
    generator_image_model: str = "gpt-image-1"
    generator_image_quality: str = "medium"  # openai 전용(low|medium|high), google_genai는 무시
    generator_image_timeout: float = 120.0  # 무거운 이미지 모델 대비 호출 타임아웃(초)
    # 이미지 편집(텍스트존 인페인팅)
    generator_image_edit_provider: str = "openai"  # openai
    generator_image_edit_model: str = "gpt-image-1"
    # 멀티모달 단일호출(이미지+카피) — GEN_MODE=multimodal 일 때만 사용
    generator_multimodal_provider: str = "openai"  # openai | google_genai
    generator_multimodal_model: str = "gpt-image-1"
    generator_font_dir: str | None = None  # 없으면 backend/assets/fonts 사용

    # JWT (Cognito 전환 전 임시)
    jwt_secret: str = "clickme-dev-secret-change-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7일


settings = Settings()
