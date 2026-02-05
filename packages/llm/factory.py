"""
LLM Factory for ClarityQL.

Provides model-agnostic LLM creation with support for multiple providers.
"""

from langchain_core.language_models import BaseChatModel


# -----------------------------
# Errors
# -----------------------------


class LLMProviderError(Exception):
    """Raised when LLM provider configuration is invalid."""

    pass


# -----------------------------
# Provider Registry
# -----------------------------


class LLMFactory:
    """
    Factory for creating LLM instances from various providers.

    Supports:
    - gemini (Google Generative AI) - default
    - openai (OpenAI)
    - anthropic (Anthropic)
    """

    # Default models for each provider
    DEFAULT_MODELS: dict[str, str] = {
        "gemini": "gemini-2.0-flash",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-sonnet-latest",
    }

    @classmethod
    def create(
        cls,
        provider: str,
        model: str | None = None,
        temperature: float = 0.0,
        api_key: str | None = None,
        **kwargs,
    ) -> BaseChatModel:
        """
        Create an LLM instance for the specified provider.

        Args:
            provider: The LLM provider ("gemini", "openai", "anthropic").
            model: Model name. Uses provider default if not specified.
            temperature: Temperature for generation (0.0 - 2.0).
            api_key: API key for the provider. Uses env var if not specified.
            **kwargs: Additional provider-specific arguments.

        Returns:
            A LangChain BaseChatModel instance.

        Raises:
            LLMProviderError: If provider is unknown or configuration is invalid.
        """
        provider = provider.lower()
        model = model or cls.DEFAULT_MODELS.get(provider)

        if model is None:
            raise LLMProviderError(f"Unknown provider: {provider}")

        match provider:
            case "gemini":
                return cls._create_gemini(model, temperature, api_key, **kwargs)
            case "openai":
                return cls._create_openai(model, temperature, api_key, **kwargs)
            case "anthropic":
                return cls._create_anthropic(model, temperature, api_key, **kwargs)
            case _:
                raise LLMProviderError(
                    f"Unknown provider: {provider}. "
                    f"Supported: gemini, openai, anthropic"
                )

    @classmethod
    def create_from_settings(cls) -> BaseChatModel:
        """
        Create an LLM instance from application settings.

        Reads configuration from environment variables via LLMSettings.

        Returns:
            A LangChain BaseChatModel instance.
        """
        # Import here to avoid circular imports
        from apps.backend.app.core.config import get_llm_settings

        settings = get_llm_settings()

        return cls.create(
            provider=settings.llm_provider,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            api_key=settings.get_api_key(),
        )

    # -------------------------
    # Provider-specific creators
    # -------------------------

    @staticmethod
    def _create_gemini(
        model: str,
        temperature: float,
        api_key: str | None,
        **kwargs,
    ) -> BaseChatModel:
        """Create a Gemini (Google Generative AI) instance."""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as e:
            raise LLMProviderError(
                "langchain-google-genai is not installed. "
                "Run: pip install langchain-google-genai"
            ) from e

        init_kwargs = {
            "model": model,
            "temperature": temperature,
            **kwargs,
        }

        if api_key:
            init_kwargs["google_api_key"] = api_key

        return ChatGoogleGenerativeAI(**init_kwargs)

    @staticmethod
    def _create_openai(
        model: str,
        temperature: float,
        api_key: str | None,
        **kwargs,
    ) -> BaseChatModel:
        """Create an OpenAI instance."""
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise LLMProviderError(
                "langchain-openai is not installed. "
                "Run: pip install langchain-openai"
            ) from e

        init_kwargs = {
            "model": model,
            "temperature": temperature,
            **kwargs,
        }

        if api_key:
            init_kwargs["api_key"] = api_key

        return ChatOpenAI(**init_kwargs)

    @staticmethod
    def _create_anthropic(
        model: str,
        temperature: float,
        api_key: str | None,
        **kwargs,
    ) -> BaseChatModel:
        """Create an Anthropic instance."""
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as e:
            raise LLMProviderError(
                "langchain-anthropic is not installed. "
                "Run: pip install langchain-anthropic"
            ) from e

        init_kwargs = {
            "model": model,
            "temperature": temperature,
            **kwargs,
        }

        if api_key:
            init_kwargs["api_key"] = api_key

        return ChatAnthropic(**init_kwargs)
