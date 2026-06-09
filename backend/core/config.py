from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_endpoint: str = "https://api.smith.langchain.com"
    langchain_api_key: str
    langchain_project: str = "clickme-v2"

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


settings = Settings()
