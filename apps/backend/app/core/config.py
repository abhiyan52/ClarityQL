"""Application configuration settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration values for the FastAPI service."""

    app_name: str = "ClarityQL API"
    environment: str = "development"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/clarityql"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
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
        env_file=".env",
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


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


@lru_cache
def get_llm_settings() -> LLMSettings:
    """Get cached LLM settings."""
    return LLMSettings()


# Convenience instances
settings = get_settings()
llm_settings = get_llm_settings()
