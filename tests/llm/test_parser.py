"""
Tests for NLQ Parser.

Tests the natural language query parser with mocked LLM responses.
"""

import pytest
from unittest.mock import MagicMock, patch

from packages.core.schema_registry.registry import get_default_registry
from packages.core.sql_ast.models import (
    AggregateFunction,
    Dimension,
    Filter,
    FilterOperator,
    Metric,
    QueryAST,
)
from packages.llm.parser import NLQParseError, NLQParser


# -----------------------------
# Fixtures
# -----------------------------


@pytest.fixture
def mock_llm():
    """Create a mock LLM that returns valid QueryAST JSON."""
    mock = MagicMock()
    return mock


@pytest.fixture
def sample_ast() -> QueryAST:
    """Create a sample valid QueryAST."""
    return QueryAST(
        metrics=[
            Metric(function=AggregateFunction.SUM, field="revenue", alias="total_revenue")
        ],
        dimensions=[Dimension(field="region")],
        filters=[
            Filter(
                field="order_date",
                operator=FilterOperator.BETWEEN,
                value=["2024-01-01", "2024-03-31"],
            )
        ],
        limit=10,
    )


@pytest.fixture
def sample_ast_json(sample_ast: QueryAST) -> str:
    """Get JSON representation of sample AST."""
    return sample_ast.model_dump_json()


# -----------------------------
# Parser Initialization Tests
# -----------------------------


class TestParserInitialization:
    """Tests for NLQParser initialization."""

    def test_uses_default_registry_when_not_provided(self, mock_llm) -> None:
        """Parser should use default registry when not provided."""
        parser = NLQParser(llm=mock_llm)
        assert parser._registry is not None

    def test_uses_provided_registry(self, mock_llm) -> None:
        """Parser should use provided registry."""
        registry = get_default_registry()
        parser = NLQParser(registry=registry, llm=mock_llm)
        assert parser._registry is registry

    def test_uses_latest_prompt_by_default(self, mock_llm) -> None:
        """Parser should use latest prompt version by default."""
        parser = NLQParser(llm=mock_llm)
        # Currently v1 is the only/latest version
        assert parser.prompt_version == "v1"

    def test_uses_specified_prompt_version(self, mock_llm) -> None:
        """Parser should use specified prompt version."""
        parser = NLQParser(llm=mock_llm, prompt_version="v1")
        assert parser.prompt_version == "v1"


# -----------------------------
# Schema Context Tests
# -----------------------------


class TestSchemaContext:
    """Tests for schema context generation."""

    def test_build_schema_context_includes_tables(self, mock_llm) -> None:
        """Schema context should include table information."""
        parser = NLQParser(llm=mock_llm)
        context = parser._build_schema_context()

        assert "orders" in context.lower()
        assert "products" in context.lower()
        assert "customers" in context.lower()

    def test_build_schema_context_includes_fields(self, mock_llm) -> None:
        """Schema context should include field information."""
        parser = NLQParser(llm=mock_llm)
        context = parser._build_schema_context()

        assert "region" in context
        assert "quantity" in context
        assert "order_date" in context

    def test_build_schema_context_includes_derived_metrics(self, mock_llm) -> None:
        """Schema context should include derived metrics."""
        parser = NLQParser(llm=mock_llm)
        context = parser._build_schema_context()

        assert "revenue" in context.lower()
        assert "derived" in context.lower()

    def test_build_schema_context_includes_field_types(self, mock_llm) -> None:
        """Schema context should include field types."""
        parser = NLQParser(llm=mock_llm)
        context = parser._build_schema_context()

        assert "string" in context.lower() or "numeric" in context.lower()


# -----------------------------
# Parsing Tests (with mocked LLM)
# -----------------------------


class TestParsing:
    """Tests for the parse method with mocked LLM."""

    def test_parse_returns_query_ast(
        self, mock_llm, sample_ast: QueryAST, sample_ast_json: str
    ) -> None:
        """Parse should return a QueryAST object."""
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = sample_ast_json
        mock_llm.invoke.return_value = mock_response

        parser = NLQParser(llm=mock_llm)

        # We need to mock the chain execution
        with patch.object(parser, "_build_chain") as mock_chain:
            mock_chain.return_value.invoke.return_value = sample_ast
            result = parser.parse("Show me total revenue by region for Q1 2024")

        assert isinstance(result, QueryAST)

    def test_parse_error_raises_nlq_parse_error(self, mock_llm) -> None:
        """Parse errors should raise NLQParseError."""
        parser = NLQParser(llm=mock_llm)

        with patch.object(parser, "_build_chain") as mock_chain:
            mock_chain.return_value.invoke.side_effect = Exception("LLM error")

            with pytest.raises(NLQParseError) as exc_info:
                parser.parse("Some query")

            assert "Failed to parse query" in str(exc_info.value)


# -----------------------------
# Chain Building Tests
# -----------------------------


class TestChainBuilding:
    """Tests for chain building."""

    def test_build_chain_creates_runnable(self, mock_llm) -> None:
        """_build_chain should create a runnable chain."""
        parser = NLQParser(llm=mock_llm)
        chain = parser._build_chain()

        # Chain should be callable/have invoke method
        assert hasattr(chain, "invoke")

    def test_build_prompt_template_returns_template(self, mock_llm) -> None:
        """_build_prompt_template should return a prompt template."""
        from langchain_core.prompts import ChatPromptTemplate

        parser = NLQParser(llm=mock_llm)
        template = parser._build_prompt_template()

        assert isinstance(template, ChatPromptTemplate)


# -----------------------------
# Properties Tests
# -----------------------------


class TestParserProperties:
    """Tests for parser properties."""

    def test_prompt_version_property(self, mock_llm) -> None:
        """prompt_version should return current version."""
        parser = NLQParser(llm=mock_llm, prompt_version="v1")
        assert parser.prompt_version == "v1"

    def test_model_info_property(self, mock_llm) -> None:
        """model_info should return model information."""
        mock_llm.model_name = "test-model"
        parser = NLQParser(llm=mock_llm)

        info = parser.model_info
        assert info == "test-model"
