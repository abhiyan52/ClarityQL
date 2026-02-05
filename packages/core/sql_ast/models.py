"""
AST models for ClarityQL.

These models define the ONLY structured format that the NLQ parser
(LLM via LangChain) is allowed to emit.

They represent analytics intent, NOT SQL syntax.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# -----------------------------
# Enums (restrict AI output)
# -----------------------------


class AggregateFunction(str, Enum):
    """Supported aggregate functions for metrics."""

    SUM = "sum"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


class FilterOperator(str, Enum):
    """Supported filter operators for WHERE clauses."""

    EQ = "="
    NOT_EQ = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    BETWEEN = "between"
    IN = "in"
    NOT_IN = "not_in"
    LIKE = "like"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class OrderDirection(str, Enum):
    """Sort direction for ORDER BY clauses."""

    ASC = "asc"
    DESC = "desc"


# -----------------------------
# Core AST Nodes
# -----------------------------


class Metric(BaseModel):
    """
    Represents an aggregated numeric value.

    Examples:
        sum(revenue)
        count(order_id)
        count_distinct(customer_id)
    """

    function: AggregateFunction
    field: str
    alias: str | None = None


class Dimension(BaseModel):
    """
    Represents a grouping dimension.

    Examples:
        region
        product_line
    """

    field: str
    alias: str | None = None


class Filter(BaseModel):
    """
    Represents a WHERE clause condition.

    Examples:
        order_date BETWEEN '2024-01-01' AND '2024-03-31'
        region = 'APAC'
        status IN ('active', 'pending')
    """

    field: str
    operator: FilterOperator
    value: Any  # Can be single value, list, or tuple (for BETWEEN)


class OrderBy(BaseModel):
    """
    Represents an ORDER BY clause.

    Example:
        ORDER BY revenue DESC
    """

    field: str
    direction: OrderDirection = OrderDirection.DESC


# -----------------------------
# Root Query AST
# -----------------------------


class QueryAST(BaseModel):
    """
    Root object representing a parsed analytics query.

    This object is produced by the NLQ parser and consumed
    by validators and the SQL compiler.
    """

    metrics: list[Metric] = Field(
        ..., description="Aggregated metrics to compute"
    )

    dimensions: list[Dimension] = Field(
        default_factory=list,
        description="Fields to group by"
    )

    filters: list[Filter] = Field(
        default_factory=list,
        description="Filter conditions"
    )

    order_by: list[OrderBy] = Field(
        default_factory=list,
        description="Ordering instructions"
    )

    limit: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Maximum number of rows to return"
    )

    @field_validator("metrics")
    @classmethod
    def at_least_one_metric(cls, v: list[Metric]) -> list[Metric]:
        if not v:
            raise ValueError("At least one metric is required")
        return v
