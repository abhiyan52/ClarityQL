"""
Tests for LLM Factory.

Tests the model-agnostic LLM creation.
"""

import pytest
from unittest.mock import patch, MagicMock

from packages.llm.factory import LLMFactory, LLMProviderError


class TestLLMFactory:
    """Tests for LLMFactory."""

    def test_default_models_defined(self) -> None:
        """Factory should have default models for all providers."""
        assert "gemini" in LLMFactory.DEFAULT_MODELS
        assert "openai" in LLMFactory.DEFAULT_MODELS
        assert "anthropic" in LLMFactory.DEFAULT_MODELS

    def test_gemini_default_model(self) -> None:
        """Gemini default model should be gemini-2.0-flash."""
        assert LLMFactory.DEFAULT_MODELS["gemini"] == "gemini-2.0-flash"

    def test_unknown_provider_raises_error(self) -> None:
        """Unknown provider should raise LLMProviderError."""
        with pytest.raises(LLMProviderError) as exc_info:
            LLMFactory.create(provider="unknown_provider")
        assert "Unknown provider" in str(exc_info.value)

    def test_provider_case_insensitive(self) -> None:
        """Provider names should be case-insensitive."""
        with patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_gemini:
            mock_gemini.return_value = MagicMock()
            LLMFactory.create(provider="GEMINI", api_key="test-key")
            mock_gemini.assert_called_once()

    def test_create_gemini(self) -> None:
        """Create should return Gemini instance for gemini provider."""
        with patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_gemini:
            mock_instance = MagicMock()
            mock_gemini.return_value = mock_instance

            result = LLMFactory.create(
                provider="gemini",
                model="gemini-2.0-flash",
                temperature=0.5,
                api_key="test-key",
            )

            assert result == mock_instance
            mock_gemini.assert_called_once_with(
                model="gemini-2.0-flash",
                temperature=0.5,
                google_api_key="test-key",
            )

    def test_create_openai(self) -> None:
        """Create should return OpenAI instance for openai provider."""
        with patch("langchain_openai.ChatOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance

            result = LLMFactory.create(
                provider="openai",
                model="gpt-4o-mini",
                temperature=0.0,
                api_key="sk-test",
            )

            assert result == mock_instance
            mock_openai.assert_called_once_with(
                model="gpt-4o-mini",
                temperature=0.0,
                api_key="sk-test",
            )

    def test_create_anthropic(self) -> None:
        """Create should return Anthropic instance for anthropic provider."""
        with patch("langchain_anthropic.ChatAnthropic") as mock_anthropic:
            mock_instance = MagicMock()
            mock_anthropic.return_value = mock_instance

            result = LLMFactory.create(
                provider="anthropic",
                model="claude-3-5-sonnet-latest",
                temperature=0.0,
                api_key="sk-ant-test",
            )

            assert result == mock_instance
            mock_anthropic.assert_called_once_with(
                model="claude-3-5-sonnet-latest",
                temperature=0.0,
                api_key="sk-ant-test",
            )

    def test_uses_default_model_when_not_specified(self) -> None:
        """Create should use default model when not specified."""
        with patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_gemini:
            mock_gemini.return_value = MagicMock()

            LLMFactory.create(provider="gemini", api_key="test-key")

            # Should use the default Gemini model
            call_kwargs = mock_gemini.call_args[1]
            assert call_kwargs["model"] == "gemini-2.0-flash"

    def test_passes_extra_kwargs(self) -> None:
        """Create should pass extra kwargs to the provider."""
        with patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_gemini:
            mock_gemini.return_value = MagicMock()

            LLMFactory.create(
                provider="gemini",
                api_key="test-key",
                max_tokens=1000,
                top_p=0.9,
            )

            call_kwargs = mock_gemini.call_args[1]
            assert call_kwargs["max_tokens"] == 1000
            assert call_kwargs["top_p"] == 0.9
