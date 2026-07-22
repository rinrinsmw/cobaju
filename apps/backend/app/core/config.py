"""Environment-backed application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_DIR = BACKEND_DIR.parents[1]


class Settings(BaseSettings):
    """Configuration values loaded from environment variables or root .env."""

    app_name: str = "Cobaju API"
    app_version: str = "0.1.0"
    app_environment: str = "development"
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
    openrouter_embedding_model: str = ""
    openrouter_chat_guardrail_model: str = ""
    openrouter_stylist_model: str = ""
    openrouter_evaluator_model: str = ""
    openrouter_timeout_seconds: float = 60.0
    guardrail_temperature: float = 0.0
    vision_temperature: float = 0.1
    chat_guardrail_temperature: float = 0.0
    stylist_temperature: float = 0.5
    stylist_repair_temperature: float = 0.1
    evaluator_temperature: float = 0.0
    stylist_max_turns: int = Field(default=8, ge=1, le=20)
    stylist_max_tool_calls: int = Field(default=8, ge=1, le=30)
    chat_guardrail_prompt_version: str = "chat-guardrail-v1"
    stylist_prompt_version: str = "stylist-v3"
    stylist_repair_prompt_version: str = "stylist-repair-v1"
    evaluator_prompt_version: str = "outfit-evaluator-v1"
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_base_url: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("LANGFUSE_HOST", "LANGFUSE_BASE_URL"),
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_task_max_retries: int = Field(default=2, ge=0)
    celery_task_retry_delay_seconds: int = Field(default=5, ge=0)
    chroma_directory: str = "./chroma"
    chroma_collection_name: str = "wardrobe_items"
    wardrobe_search_limit: int = Field(default=5, ge=1, le=15)
    styling_candidates_per_category: int = Field(default=3, ge=1, le=5)

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
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

    @property
    def resolved_chroma_directory(self) -> Path:
        """Resolve relative Chroma storage from the backend directory."""

        chroma_path = Path(self.chroma_directory)
        if chroma_path.is_absolute():
            return chroma_path
        return (BACKEND_DIR / chroma_path).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return one shared settings object for the application process."""

    return Settings()
