"""Environment-backed application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_DIR = BACKEND_DIR.parents[1]


class Settings(BaseSettings):
    """Configuration values loaded from environment variables or root .env."""

    app_name: str = "Cobaju API"
    app_version: str = "0.1.0"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    database_url: str = "sqlite:///./cobaju.db"
    jwt_secret_key: SecretStr = SecretStr("")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    upload_directory: str = "./uploads"
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_guardrail_model: str = ""
    openrouter_vision_model: str = ""
    openrouter_timeout_seconds: float = 60.0
    guardrail_temperature: float = 0.0
    vision_temperature: float = 0.1
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_base_url: str = "https://cloud.langfuse.com"
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_task_max_retries: int = Field(default=2, ge=0)
    celery_task_retry_delay_seconds: int = Field(default=5, ge=0)

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_database_url(self) -> str:
        """Resolve relative SQLite files from the backend directory.

        This keeps Moonrepo and native uv commands pointed at the same file,
        even when they start from different working directories.
        """

        prefix = "sqlite:///"
        database_path = self.database_url.removeprefix(prefix)

        if (
            not self.database_url.startswith(prefix)
            or self.database_url.startswith("sqlite:////")
            or database_path == ":memory:"
        ):
            return self.database_url

        absolute_path = (BACKEND_DIR / database_path).resolve()
        return f"{prefix}{absolute_path}"

    @property
    def resolved_upload_directory(self) -> Path:
        """Resolve relative upload directories from the backend directory."""

        upload_path = Path(self.upload_directory)
        if upload_path.is_absolute():
            return upload_path
        return (BACKEND_DIR / upload_path).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return one shared settings object for the application process."""

    return Settings()
