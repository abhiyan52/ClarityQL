"""
NLQ Parser for ClarityQL.

Converts natural language queries to QueryAST using LLMs.
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser

from packages.core.schema_registry.registry import (
    SchemaRegistry,
    get_default_registry,
)
from packages.core.sql_ast.models import QueryAST
from packages.llm.factory import LLMFactory
from packages.llm.prompts import PromptRegistry


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
            chain = self._build_chain()
            result = chain.invoke({"query": user_query})
            return result
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
            chain_without_parser = prompt | self._llm

            # Get raw response
            raw_response = chain_without_parser.invoke({"query": user_query})
            raw_content = raw_response.content

            # Parse the response
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
