from pathlib import Path

from pydantic import Field
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
    LANGSMITH_TRACING_V2: bool = True
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: str = ""
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


settings = Settings()
