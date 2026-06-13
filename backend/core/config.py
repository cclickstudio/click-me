from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from domain.billing.toss_client import require_test_key

BACKEND_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_ROOT / ".env"


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
    LANGSMITH_TRACING_V2: bool = True
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: str = ""  # 미설정 시 main.py가 트레이싱 비활성화
    LANGSMITH_PROJECT: str = "clickme-v2"

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

    # Meta / Instagram Content Publishing (Generator) — 비우면 Mock 게시 모드
    meta_access_token: str | None = None
    meta_ig_user_id: str | None = None
    meta_graph_api_version: str = "v21.0"

    # Generator (광고 생성)
    generator_text_model: str = "gpt-4o"
    generator_image_model: str = "gpt-image-1"
    generator_image_quality: str = "medium"

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
