"""
Tests for Prompt Versioning System.

Tests the prompt registry and prompt versions.
"""

import pytest

from packages.llm.prompts.base import BasePrompt
from packages.llm.prompts.registry import PromptRegistry
from packages.llm.prompts.versions.v1 import PromptV1


class TestPromptRegistry:
    """Tests for PromptRegistry."""

    def test_v1_is_registered(self) -> None:
        """PromptV1 should be registered by default."""
        versions = PromptRegistry.list_versions()
        assert "v1" in versions

    def test_get_v1(self) -> None:
        """Should be able to get v1 prompt."""
        prompt = PromptRegistry.get("v1")
        assert isinstance(prompt, PromptV1)
        assert prompt.version == "v1"

    def test_get_latest(self) -> None:
        """Latest should return the highest version."""
        prompt = PromptRegistry.get("latest")
        # Currently v1 is the only version, so it should be v1
        assert isinstance(prompt, BasePrompt)
        assert prompt.version == "v1"

    def test_unknown_version_raises_error(self) -> None:
        """Unknown version should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            PromptRegistry.get("v999")
        assert "Unknown prompt version" in str(exc_info.value)

    def test_list_versions(self) -> None:
        """list_versions should return sorted list of versions."""
        versions = PromptRegistry.list_versions()
        assert isinstance(versions, list)
        assert len(versions) >= 1
        assert "v1" in versions


class TestPromptV1:
    """Tests for PromptV1."""

    def test_version_attribute(self) -> None:
        """V1 should have correct version attribute."""
        prompt = PromptV1()
        assert prompt.version == "v1"

    def test_description_attribute(self) -> None:
        """V1 should have a description."""
        prompt = PromptV1()
        assert prompt.description is not None
        assert len(prompt.description) > 0

    def test_build_returns_chat_prompt_template(self) -> None:
        """build() should return a ChatPromptTemplate."""
        from langchain_core.prompts import ChatPromptTemplate

        prompt = PromptV1()
        template = prompt.build(
            schema_context="Test schema",
            format_instructions="Test format",
        )

        assert isinstance(template, ChatPromptTemplate)

    def test_build_includes_schema_placeholder(self) -> None:
        """Built template should have schema input variable."""
        prompt = PromptV1()
        template = prompt.build(
            schema_context="Test schema",
            format_instructions="Test format",
        )

        # The template should have 'query' as an input variable
        # (schema and format_instructions are partialed)
        assert "query" in template.input_variables

    def test_build_includes_format_instructions(self) -> None:
        """Built template should include format instructions."""
        prompt = PromptV1()
        template = prompt.build(
            schema_context="Test schema",
            format_instructions="OUTPUT AS JSON",
        )

        # Format instructions should be partialed into the template
        # We can check by looking at the partial variables
        assert "format_instructions" in template.partial_variables

    def test_repr(self) -> None:
        """Prompt should have a useful repr."""
        prompt = PromptV1()
        repr_str = repr(prompt)
        assert "PromptV1" in repr_str
        assert "v1" in repr_str


class TestCustomPromptRegistration:
    """Tests for registering custom prompts."""

    def test_register_custom_prompt(self) -> None:
        """Should be able to register a custom prompt."""

        @PromptRegistry.register
        class TestPrompt(BasePrompt):
            version = "test"
            description = "Test prompt"

            def build(self, schema_context, format_instructions):
                from langchain_core.prompts import ChatPromptTemplate
                return ChatPromptTemplate.from_messages([
                    ("system", "Test"),
                    ("human", "{query}"),
                ])

        # Clean up after test
        try:
            prompt = PromptRegistry.get("test")
            assert prompt.version == "test"
        finally:
            # Remove test prompt from registry
            if "test" in PromptRegistry._prompts:
                del PromptRegistry._prompts["test"]
