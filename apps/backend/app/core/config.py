"""Application configuration settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Find project root (where .env file lives)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # app/core -> app -> backend
_PROJECT_ROOT = _BACKEND_DIR.parent.parent  # backend -> apps -> project root
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Configuration values for the FastAPI service."""

    app_name: str = "ClarityQL API"
    environment: str = "development"

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/clarityql"
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/clarityql"
    )

    # JWT Settings
    jwt_secret_key: str = Field(
        default="your-super-secret-key-change-in-production",
        description="Secret key for JWT encoding/decoding",
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=60 * 24, description="Token expiry in minutes")

    # Celery Settings
    celery_broker_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        description="Celery broker URL (Redis)",
    )
    celery_result_backend: str = Field(
        default="db+postgresql+psycopg://postgres:postgres@127.0.0.1:5432/clarityql",
        description="Celery result backend (Database)",
    )

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class LLMSettings(BaseSettings):
    """LLM provider configuration settings."""

    # Provider selection
    llm_provider: str = Field(
        default="gemini",
        description="LLM provider: gemini, openai, or anthropic",
    )
    llm_model: str = Field(
        default="gemini-2.0-flash",
        description="Model name for the selected provider",
    )
    llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature for LLM responses",
    )
    llm_request_timeout_seconds: float | None = Field(
        default=60.0,
        ge=1.0,
        description="Timeout in seconds for LLM requests",
    )

    # Provider API keys
    google_api_key: str | None = Field(
        default=None,
        description="Google API key for Gemini",
    )
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key",
    )
    anthropic_api_key: str | None = Field(
        default=None,
        description="Anthropic API key",
    )

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_api_key(self) -> str | None:
        """Get the API key for the currently configured provider."""
        match self.llm_provider:
            case "gemini":
                return self.google_api_key
            case "openai":
                return self.openai_api_key
            case "anthropic":
                return self.anthropic_api_key
            case _:
                return None


class EmbeddingSettings(BaseSettings):
    """Embedding model configuration settings."""

    embedding_model: str = Field(
        default="intfloat/multilingual-e5-large-instruct",
        description="Sentence Transformer model name for embeddings",
    )
    embedding_dimension: int = Field(
        default=1024,
        description="Embedding vector dimension (must match model output)",
    )
    embedding_normalize: bool = Field(
        default=True,
        description="Whether to normalize embeddings to unit length",
    )
    embedding_cache_dir: str | None = Field(
        default=None,
        description="Optional directory to cache downloaded models",
    )

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


@lru_cache
def get_llm_settings() -> LLMSettings:
    """Get cached LLM settings."""
    return LLMSettings()


@lru_cache
def get_embedding_settings() -> EmbeddingSettings:
    """Get cached embedding settings."""
    return EmbeddingSettings()


# Convenience instances
settings = get_settings()
llm_settings = get_llm_settings()
embedding_settings = get_embedding_settings()
