from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    database_url: str
    database_url_sync: str

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    retell_api_key: str = ""
    retell_agent_id: str = ""
    retell_from_number: str = ""
    retell_webhook_secret: str = ""

    openai_api_key: str = ""
    eval_model: str = "gpt-4o-mini"

    default_pass_threshold: float = 0.7
    max_calls_per_run: int = 50
    max_cost_per_run_usd: float = 10.0
    max_call_duration_sec: int = 600

    # Comma-separated list of allowed origins for the Next.js UI (SSE requires CORS).
    ui_cors_origins: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
