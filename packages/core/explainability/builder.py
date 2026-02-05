"""
Explainability Builder for ClarityQL.

Builds a structured, human-readable explanation of how a query
was interpreted, based on the AST and JoinPlan.

This module is deterministic and does NOT inspect SQL.
"""

from dataclasses import dataclass, field

from packages.core.sql_ast.models import QueryAST, Filter, FilterOperator
from packages.core.sql_ast.join_resolver import JoinPlan


@dataclass
class QueryExplanation:
    """Structured explanation of a parsed query."""

    aggregates: list[str] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)
    limit: int | None = None
    source_tables: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "aggregates": self.aggregates,
            "groupBy": self.group_by,
            "filters": self.filters,
            "orderBy": self.order_by,
            "limit": self.limit,
            "sourceTables": self.source_tables,
        }

    def to_natural_language(self) -> str:
        """Generate a natural language description of the query."""
        parts = []

        # Describe what we're calculating
        if self.aggregates:
            agg_text = ", ".join(self.aggregates)
            parts.append(f"Calculating {agg_text}")

        # Describe grouping
        if self.group_by:
            group_text = ", ".join(self.group_by)
            parts.append(f"grouped by {group_text}")

        # Describe filters
        if self.filters:
            filter_text = " and ".join(self.filters)
            parts.append(f"where {filter_text}")

        # Describe ordering
        if self.order_by:
            order_text = ", ".join(self.order_by)
            parts.append(f"ordered by {order_text}")

        # Describe limit
        if self.limit:
            parts.append(f"limited to {self.limit} results")

        # Describe data sources
        if self.source_tables:
            table_text = ", ".join(self.source_tables)
            parts.append(f"using data from {table_text}")

        return " ".join(parts) + "." if parts else "No query to explain."


class ExplainabilityBuilder:
    """Builds explanations from AST and JoinPlan."""

    def build(self, ast: QueryAST, join_plan: JoinPlan) -> QueryExplanation:
        """
        Build an explanation object from AST + JoinPlan.

        Args:
            ast: The parsed query abstract syntax tree
            join_plan: The resolved join plan

        Returns:
            QueryExplanation with structured explanation data
        """
        return QueryExplanation(
            aggregates=self._build_aggregates(ast),
            group_by=self._build_group_by(ast),
            filters=self._build_filters(ast),
            order_by=self._build_order_by(ast),
            limit=ast.limit,
            source_tables=self._build_source_tables(join_plan),
        )

    def build_dict(self, ast: QueryAST, join_plan: JoinPlan) -> dict:
        """Build explanation and return as dictionary."""
        return self.build(ast, join_plan).to_dict()

    # -------------------------
    # Section builders
    # -------------------------

    def _build_aggregates(self, ast: QueryAST) -> list[str]:
        """Build list of aggregate descriptions."""
        aggregates = []

        for metric in ast.metrics:
            func_name = metric.function.value.upper()
            field_name = metric.alias or metric.field
            aggregates.append(f"{func_name}({metric.field})" + (
                f" as {metric.alias}" if metric.alias else ""
            ))

        return aggregates

    def _build_group_by(self, ast: QueryAST) -> list[str]:
        """Build list of GROUP BY fields."""
        return [
            dim.alias or dim.field
            for dim in ast.dimensions
        ]

    def _build_filters(self, ast: QueryAST) -> list[str]:
        """Build list of filter descriptions."""
        return [self._format_filter(f) for f in ast.filters]

    def _build_order_by(self, ast: QueryAST) -> list[str]:
        """Build list of ORDER BY descriptions."""
        return [
            f"{order.field} {order.direction.value.upper()}"
            for order in ast.order_by
        ]

    def _build_source_tables(self, join_plan: JoinPlan) -> list[str]:
        """Build sorted list of source tables."""
        tables = {join_plan.base_table}

        for join in join_plan.joins:
            tables.add(join.right_table)

        return sorted(tables)

    # -------------------------
    # Formatting helpers
    # -------------------------

    def _format_filter(self, f: Filter) -> str:
        """Format a single filter as a readable string."""
        op = f.operator

        match op:
            case FilterOperator.BETWEEN:
                start, end = f.value
                return f"{f.field} between {start} and {end}"

            case FilterOperator.IN:
                values = ", ".join(repr(v) for v in f.value)
                return f"{f.field} in ({values})"

            case FilterOperator.NOT_IN:
                values = ", ".join(repr(v) for v in f.value)
                return f"{f.field} not in ({values})"

            case FilterOperator.IS_NULL:
                return f"{f.field} is null"

            case FilterOperator.IS_NOT_NULL:
                return f"{f.field} is not null"

            case FilterOperator.LIKE:
                return f"{f.field} like '{f.value}'"

            case FilterOperator.EQ:
                return f"{f.field} = {repr(f.value)}"

            case FilterOperator.NOT_EQ:
                return f"{f.field} != {repr(f.value)}"

            case FilterOperator.GT:
                return f"{f.field} > {f.value}"

            case FilterOperator.LT:
                return f"{f.field} < {f.value}"

            case FilterOperator.GTE:
                return f"{f.field} >= {f.value}"

            case FilterOperator.LTE:
                return f"{f.field} <= {f.value}"

            case _:
                return f"{f.field} {op.value} {f.value}"
