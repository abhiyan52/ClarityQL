"""Version 1 of the intent classification prompt."""

from langchain_core.prompts import ChatPromptTemplate

from packages.core.conversation.prompts.base import BaseIntentPrompt
from packages.core.conversation.prompts.registry import IntentPromptRegistry


@IntentPromptRegistry.register
class IntentPromptV1(BaseIntentPrompt):
    """
    Version 1 of the intent classification prompt.

    This prompt classifies user queries as REFINE or RESET
    based on the previous query context.
    """

    version = "v1"
    description = "Initial intent classification prompt with explicit examples"

    def build(self) -> ChatPromptTemplate:
        """Build the intent classification prompt template."""

        system_message = """You are an intent classifier for an analytics query system.

Your job is to determine if a new user query:
- REFINE: Modifies, filters, or adjusts the PREVIOUS query (e.g., adding filters, changing order, narrowing scope)
- RESET: Starts a completely NEW and unrelated analysis

REFINE indicators (query DEPENDS on previous context):
- Adding a filter: "only for Europe", "just the top 10", "where status is active"
- Changing sort order: "sort by date instead", "ascending order"
- Adding a dimension: "also break down by month", "group by category too"
- Modifying limit: "show me more", "just top 5"
- Narrowing scope: "for Q1 only", "excluding returns"
- Referencing previous: "for that", "same but", "also show"

RESET indicators (query is INDEPENDENT of previous context):
- Different metrics: "customer count" when previous was "revenue"
- Different subject: "product categories" when previous was "orders by region"
- Complete new question: "what is the average order value"
- No logical connection to previous query

Examples:

Previous: metrics=sum(revenue), dimensions=[region, order_date]
New: "only for Europe" → REFINE (adds filter, keeps dimensions)

Previous: metrics=sum(revenue), dimensions=[region]
New: "sort by revenue ascending" → REFINE (changes order)

Previous: metrics=sum(revenue), dimensions=[region]
New: "show customer count by segment" → RESET (different metric and dimension)

Previous: metrics=count(orders), dimensions=[product]
New: "what was the total revenue last quarter" → RESET (different analysis)

Respond with EXACTLY one word: REFINE or RESET"""

        user_message = """Previous query:
{previous_query_summary}

New user query: "{new_query}"

Classification:"""

        return ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", user_message),
        ])
