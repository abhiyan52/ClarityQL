"""
NLQ Parser for ClarityQL.

Converts natural language queries to QueryAST using LLMs.
"""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser

from packages.core.schema_registry.registry import (
    SchemaRegistry,
    get_default_registry,
)
from packages.core.sql_ast.models import QueryAST
from packages.llm.factory import LLMFactory
from packages.llm.prompts import PromptRegistry

logger = logging.getLogger(__name__)

# ANSI colors for visibility in logs
_COLOR_MAGENTA = "\033[95m"
_COLOR_CYAN = "\033[96m"
_COLOR_YELLOW = "\033[93m"
_COLOR_GREEN = "\033[92m"
_COLOR_RESET = "\033[0m"

_WORD_PATTERN = re.compile(r"\S+")


# -----------------------------
# Errors
# -----------------------------


class NLQParseError(Exception):
    """Raised when NLQ parsing fails."""

    pass


# -----------------------------
# Parser
# -----------------------------


class NLQParser:
    """
    Natural Language Query parser.

    Converts user queries in natural language to structured QueryAST
    objects using an LLM.
    """

    def __init__(
        self,
        registry: SchemaRegistry | None = None,
        llm: BaseChatModel | None = None,
        prompt_version: str = "latest",
    ):
        """
        Initialize the NLQ parser.

        Args:
            registry: Schema registry for field/table metadata.
                     Uses default registry if not provided.
            llm: LangChain chat model to use.
                Uses LLMFactory.create_from_settings() if not provided.
            prompt_version: Version of the prompt to use (e.g., "v1", "latest").
        """
        self._registry = registry or get_default_registry()
        self._llm = llm or LLMFactory.create_from_settings()
        self._prompt = PromptRegistry.get(prompt_version)
        self._output_parser = PydanticOutputParser(pydantic_object=QueryAST)

    def parse(self, user_query: str) -> QueryAST:
        """
        Parse a natural language query into a QueryAST.

        Args:
            user_query: The user's natural language query.

        Returns:
            A validated QueryAST object.

        Raises:
            NLQParseError: If parsing fails.
        """
        try:
            ast, _ = self.parse_with_raw(user_query)
            return ast
        except Exception as e:
            raise NLQParseError(f"Failed to parse query: {e}") from e

    def parse_with_raw(self, user_query: str) -> tuple[QueryAST, str]:
        """
        Parse a query and return both the AST and raw LLM response.

        Useful for debugging and logging.

        Args:
            user_query: The user's natural language query.

        Returns:
            Tuple of (QueryAST, raw_response_string).

        Raises:
            NLQParseError: If parsing fails.
        """
        try:
            prompt = self._build_prompt_template()
            messages = prompt.format_messages(query=user_query)
            prompt_text = self._format_messages(messages)
            prompt_tokens_est = self._estimate_tokens(prompt_text)
            start_time = time.time()
            start_time_str = self._format_timestamp(start_time)

            self._log_llm_request(prompt_text, prompt_tokens_est, start_time_str)

            chain_without_parser = prompt | self._llm
            raw_response = chain_without_parser.invoke({"query": user_query})
            raw_content = self._normalize_content(raw_response.content)

            response_tokens_est = self._estimate_tokens(raw_content)
            usage = self._extract_usage(raw_response)
            end_time = time.time()
            end_time_str = self._format_timestamp(end_time)
            duration_ms = int((end_time - start_time) * 1000)
            self._log_llm_response(
                raw_content,
                prompt_tokens_est,
                response_tokens_est,
                usage,
                end_time_str,
                duration_ms,
            )

            ast = self._output_parser.parse(raw_content)
            return ast, raw_content
        except Exception as e:
            raise NLQParseError(f"Failed to parse query: {e}") from e

    # -------------------------
    # Chain Building
    # -------------------------

    def _build_chain(self):
        """Build the LangChain pipeline."""
        prompt = self._build_prompt_template()
        return prompt | self._llm | self._output_parser

    def _build_prompt_template(self):
        """Build the prompt template with schema context."""
        schema_context = self._build_schema_context()
        format_instructions = self._output_parser.get_format_instructions()

        return self._prompt.build(
            schema_context=schema_context,
            format_instructions=format_instructions,
        )

    def _build_schema_context(self) -> str:
        """
        Build a description of the available schema for the LLM.

        Uses the schema registry to generate a human-readable
        description of tables, fields, and derived metrics.
        """
        lines = []

        # List tables and their fields
        lines.append("TABLES AND FIELDS:")
        for table_name in self._registry.list_tables():
            table = self._registry.get_table(table_name)
            if table:
                # Get field names and types
                field_info = []
                for field_name, field_meta in table.fields.items():
                    type_str = field_meta.field_type.value
                    agg_str = " [aggregatable]" if field_meta.aggregatable else ""
                    desc_str = f" - {field_meta.description}" if field_meta.description else ""
                    # Include allowed values for categorical fields
                    if field_meta.allowed_values:
                        values_str = ", ".join(f'"{v}"' for v in field_meta.allowed_values)
                        desc_str += f" [ALLOWED VALUES: {values_str}]"
                    field_info.append(f"    - {field_name} ({type_str}{agg_str}){desc_str}")

                lines.append(f"  {table_name}:")
                lines.extend(field_info)

        # List derived metrics
        derived_metrics = self._registry.list_derived_metrics()
        if derived_metrics:
            lines.append("\nDERIVED METRICS (pre-calculated):")
            for metric_name in derived_metrics:
                metric = self._registry.get_derived_metric(metric_name)
                if metric:
                    desc = f" - {metric.description}" if metric.description else ""
                    lines.append(f"  - {metric_name}{desc}")

        return "\n".join(lines)

    # -------------------------
    # Properties
    # -------------------------

    @property
    def prompt_version(self) -> str:
        """Get the current prompt version."""
        return self._prompt.version

    @property
    def model_info(self) -> str:
        """Get information about the current LLM."""
        # Most LangChain models have these attributes
        model_name = getattr(self._llm, "model_name", None)
        model = getattr(self._llm, "model", None)
        return model_name or model or str(type(self._llm).__name__)

    # -------------------------
    # Logging Helpers
    # -------------------------

    def _format_messages(self, messages: list[Any]) -> str:
        """Format prompt messages for logging."""
        formatted = []
        for msg in messages:
            role = getattr(msg, "type", "unknown").upper()
            content = getattr(msg, "content", "")
            formatted.append(f"{role}:\n{content}")
        return "\n\n".join(formatted)

    def _normalize_content(self, content: Any) -> str:
        """Normalize LLM content to a string for parsing/logging."""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            return "".join(parts).strip()
        return str(content)

    def _estimate_tokens(self, text: Any) -> int:
        """Estimate token count using a simple word-based heuristic."""
        if text is None:
            return 0
        if not isinstance(text, str):
            text = str(text)
        if not text:
            return 0
        return max(1, int(len(_WORD_PATTERN.findall(text)) * 1.3))

    def _extract_usage(self, response: Any) -> dict[str, Any]:
        """Extract token usage metadata from a LangChain response."""
        usage: dict[str, Any] = {}

        usage_metadata = getattr(response, "usage_metadata", None)
        if isinstance(usage_metadata, dict):
            usage.update(usage_metadata)

        response_metadata = getattr(response, "response_metadata", None)
        if isinstance(response_metadata, dict):
            token_usage = response_metadata.get("token_usage") or response_metadata.get("usage")
            if isinstance(token_usage, dict):
                usage.update(token_usage)

        return usage

    def _log_llm_request(
        self,
        prompt_text: str,
        prompt_tokens_est: int,
        start_time_str: str,
    ) -> None:
        header = (
            f"{_COLOR_MAGENTA}[NLQ_LLM_REQUEST]{_COLOR_RESET} "
            f"{_COLOR_CYAN}model={self.model_info}{_COLOR_RESET} "
            f"{_COLOR_YELLOW}prompt_version={self.prompt_version}{_COLOR_RESET} "
            f"{_COLOR_GREEN}prompt_tokens_est={prompt_tokens_est}{_COLOR_RESET} "
            f"{_COLOR_YELLOW}start_time={start_time_str}{_COLOR_RESET}"
        )
        body = f"{_COLOR_CYAN}{prompt_text}{_COLOR_RESET}"
        logger.info("%s\n%s", header, body)
        print(f"{header}\n{body}")

    def _log_llm_response(
        self,
        raw_content: str,
        prompt_tokens_est: int,
        response_tokens_est: int,
        usage: dict[str, Any],
        end_time_str: str,
        duration_ms: int,
    ) -> None:
        usage_total = usage.get("total_tokens")
        usage_input = usage.get("input_tokens") or usage.get("prompt_tokens")
        usage_output = usage.get("output_tokens") or usage.get("completion_tokens")

        header = (
            f"{_COLOR_MAGENTA}[NLQ_LLM_RESPONSE]{_COLOR_RESET} "
            f"{_COLOR_CYAN}model={self.model_info}{_COLOR_RESET} "
            f"{_COLOR_GREEN}prompt_tokens_est={prompt_tokens_est}{_COLOR_RESET} "
            f"{_COLOR_GREEN}response_tokens_est={response_tokens_est}{_COLOR_RESET} "
            f"{_COLOR_YELLOW}end_time={end_time_str}{_COLOR_RESET} "
            f"{_COLOR_YELLOW}duration_ms={duration_ms}{_COLOR_RESET}"
        )

        if usage_total is not None:
            header += (
                f" {_COLOR_YELLOW}usage_total={usage_total}{_COLOR_RESET}"
            )
        if usage_input is not None or usage_output is not None:
            header += (
                f" {_COLOR_YELLOW}usage_in={usage_input} usage_out={usage_output}{_COLOR_RESET}"
            )

        body = f"{_COLOR_CYAN}{raw_content}{_COLOR_RESET}"
        logger.info("%s\n%s", header, body)
        print(f"{header}\n{body}")

    def _format_timestamp(self, ts: float) -> str:
        """Format a timestamp for log output."""
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
