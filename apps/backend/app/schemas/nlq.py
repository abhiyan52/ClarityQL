"""NLQ query schemas."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class VisualizationSchema(BaseModel):
    """Schema for visualization specification."""

    type: Literal["table", "bar", "line", "multi-line", "kpi"]
    x: str | None = None
    y: str | None = None
    series: str | None = None


class MetricSchema(BaseModel):
    """Schema for a metric in the AST."""

    function: str
    field: str
    alias: str | None = None


class DimensionSchema(BaseModel):
    """Schema for a dimension in the AST."""

    field: str
    alias: str | None = None


class FilterSchema(BaseModel):
    """Schema for a filter in the AST."""

    field: str
    operator: str
    value: Any


class OrderBySchema(BaseModel):
    """Schema for order by in the AST."""

    field: str
    direction: str = "desc"


class ASTSchema(BaseModel):
    """Schema for the QueryAST."""

    metrics: list[MetricSchema]
    dimensions: list[DimensionSchema] = []
    filters: list[FilterSchema] = []
    order_by: list[OrderBySchema] = []
    limit: int = 50


class ExplainabilitySchema(BaseModel):
    """Schema for query explainability."""

    aggregates: list[str] = []
    group_by: list[str] = []
    filters: list[str] = []
    order_by: list[str] = []
    limit: int | None = None
    source_tables: list[str] = []
    natural_language: str | None = None


class NLQQueryRequest(BaseModel):
    """Request schema for NLQ query."""

    query: str = Field(min_length=1, max_length=1000)
    conversation_id: UUID | None = None


class NLQQueryResponse(BaseModel):
    """Response schema for NLQ query."""

    conversation_id: UUID
    ast: ASTSchema
    explainability: ExplainabilitySchema
    visualization: VisualizationSchema
    sql: str | None = None
    columns: list[str]
    rows: list[list[Any]]
    intent: str | None = None  # "refine" or "reset"
    merged: bool = False


class NLQResetResponse(BaseModel):
    """Response schema for conversation reset."""

    conversation_id: UUID
    message: str = "Conversation context cleared"


class NLQErrorResponse(BaseModel):
    """Error response schema."""

    error: str
    error_type: str
    conversation_id: UUID | None = None
