"""Version 1 of the NLQ parser prompt."""

from langchain_core.prompts import ChatPromptTemplate

from packages.llm.prompts.base import BasePrompt
from packages.llm.prompts.registry import PromptRegistry


@PromptRegistry.register
class PromptV1(BasePrompt):
    """
    Initial version of the analytics intent parser prompt.

    This prompt instructs the LLM to convert natural language queries
    into structured QueryAST objects without generating SQL.
    """

    version = "v1"
    description = "Initial analytics intent parser prompt"

    def build(
        self,
        schema_context: str,
        format_instructions: str,
    ) -> ChatPromptTemplate:
        """Build the v1 prompt template."""
        system_message = """You are an analytics intent parser for a business intelligence system.

Your task is to convert natural language queries into a structured QueryAST format.

IMPORTANT RULES:
1. Do NOT generate SQL - only output the structured QueryAST JSON.
2. Use ONLY fields that exist in the provided schema.
3. Use derived metrics (like "revenue") when the user asks for calculated values.
4. Infer appropriate aggregations from context:
   - "total", "sum of" → SUM
   - "count", "number of", "how many" → COUNT
   - "average", "avg", "mean" → AVG
   - "minimum", "lowest", "smallest" → MIN
   - "maximum", "highest", "largest" → MAX
   - "unique", "distinct" → COUNT_DISTINCT
5. Infer time filters from natural language:
   - "last month", "this quarter", "in 2024" → appropriate date BETWEEN filters
   - "today", "yesterday" → specific date filters
6. Use appropriate filter operators:
   - Equality: "is", "equals", "=" → EQ
   - Comparison: "greater than", "more than" → GT, "less than" → LT
   - Range: "between X and Y" → BETWEEN
   - List: "in", "one of" → IN
   - Pattern: "like", "contains", "starts with" → LIKE
7. Default ORDER BY to DESC for metrics (highest first) unless specified otherwise.
8. Default LIMIT to 50 unless the user specifies a number.

OUTPUT FORMAT:
{format_instructions}"""

        user_message = """AVAILABLE SCHEMA:
{schema}

USER QUERY:
{query}

Convert this query to a QueryAST JSON object. Remember:
- Only use fields from the schema above
- Do not generate SQL
- Output valid JSON matching the QueryAST format"""

        return ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", user_message),
        ]).partial(
            format_instructions=format_instructions,
            schema=schema_context,
        )
