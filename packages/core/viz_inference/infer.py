"""
Visualization Inference Module.

This module infers the appropriate visualization type from a QueryAST.
The inference is DETERMINISTIC and rule-based - no LLMs, no guessing.

Rules:
1. No dimensions, metrics only → KPI
2. 1 dimension + 1 metric:
   - Date dimension → line chart
   - Categorical dimension → bar chart
3. 2 dimensions (one must be date) → multi-line chart
4. Anything else → table only
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.core.sql_ast.models import QueryAST
    from packages.core.schema_registry.registry import SchemaRegistry


class VisualizationType(str, Enum):
    """Supported visualization types."""

    TABLE = "table"
    BAR = "bar"
    LINE = "line"
    MULTI_LINE = "multi-line"
    KPI = "kpi"


@dataclass(frozen=True)
class VisualizationSpec:
    """
    Specification for how to visualize query results.

    This is a contract between backend and frontend.
    The frontend MUST NOT decide the chart type - it only renders.

    Attributes:
        type: The visualization type to render.
        x: The dimension field for the x-axis (None for KPI).
        y: The metric field for the y-axis (None for KPI).
        series: The dimension field for series grouping (multi-line only).
    """

    type: VisualizationType
    x: str | None = None
    y: str | None = None
    series: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "type": self.type.value,
            "x": self.x,
            "y": self.y,
            "series": self.series,
        }


def _is_date_field(field_name: str, registry: "SchemaRegistry") -> bool:
    """
    Check if a field is a date or timestamp type.

    Args:
        field_name: The semantic field name.
        registry: Schema registry for field lookup.

    Returns:
        True if the field is DATE or TIMESTAMP type.
    """
    from packages.core.schema_registry.registry import FieldType

    field_meta = registry.get_field(field_name)
    if field_meta is None:
        return False

    return field_meta.field_type in (FieldType.DATE, FieldType.TIMESTAMP)


def _get_metric_name(ast: "QueryAST") -> str | None:
    """
    Get the display name for the first metric.

    Uses alias if available, otherwise constructs from function and field.
    """
    if not ast.metrics:
        return None

    metric = ast.metrics[0]
    if metric.alias:
        return metric.alias

    # Construct name like "sum_revenue" or "count_orders"
    return f"{metric.function.value}_{metric.field}"


def _get_dimension_name(ast: "QueryAST", index: int = 0) -> str | None:
    """
    Get the display name for a dimension at the given index.

    Uses alias if available, otherwise uses the field name.
    """
    if index >= len(ast.dimensions):
        return None

    dim = ast.dimensions[index]
    return dim.alias or dim.field


def infer_visualization(
    ast: "QueryAST",
    registry: "SchemaRegistry",
) -> VisualizationSpec:
    """
    Infer the appropriate visualization from a QueryAST.

    This function implements deterministic rules based on:
    - Number of dimensions
    - Number of metrics
    - Field types (date vs categorical)

    Rules:
    1. No dimensions (metrics only) → KPI
    2. 1 dimension + metrics:
       - Date dimension → line chart
       - Categorical dimension → bar chart
    3. 2 dimensions (one date, one categorical) → multi-line chart
    4. Anything else → table only

    Args:
        ast: The QueryAST to analyze.
        registry: Schema registry for field type lookup.

    Returns:
        VisualizationSpec with the recommended visualization.
    """
    num_dimensions = len(ast.dimensions)
    num_metrics = len(ast.metrics)

    # Must have at least one metric (enforced by AST validation)
    if num_metrics == 0:
        return VisualizationSpec(type=VisualizationType.TABLE)

    metric_name = _get_metric_name(ast)

    # Rule 1: No dimensions → KPI
    if num_dimensions == 0:
        return VisualizationSpec(
            type=VisualizationType.KPI,
            y=metric_name,
        )

    # Rule 2: Single dimension
    if num_dimensions == 1:
        dim_field = ast.dimensions[0].field
        dim_name = _get_dimension_name(ast, 0)
        is_date = _is_date_field(dim_field, registry)

        if is_date:
            # Date dimension → line chart
            return VisualizationSpec(
                type=VisualizationType.LINE,
                x=dim_name,
                y=metric_name,
            )
        else:
            # Categorical dimension → bar chart
            return VisualizationSpec(
                type=VisualizationType.BAR,
                x=dim_name,
                y=metric_name,
            )

    # Rule 3: Two dimensions - one must be date for multi-line
    if num_dimensions == 2:
        dim0_field = ast.dimensions[0].field
        dim1_field = ast.dimensions[1].field
        dim0_is_date = _is_date_field(dim0_field, registry)
        dim1_is_date = _is_date_field(dim1_field, registry)

        # Exactly one dimension should be date for multi-line
        if dim0_is_date and not dim1_is_date:
            # First dimension is date (x-axis), second is series
            return VisualizationSpec(
                type=VisualizationType.MULTI_LINE,
                x=_get_dimension_name(ast, 0),
                y=metric_name,
                series=_get_dimension_name(ast, 1),
            )
        elif dim1_is_date and not dim0_is_date:
            # Second dimension is date (x-axis), first is series
            return VisualizationSpec(
                type=VisualizationType.MULTI_LINE,
                x=_get_dimension_name(ast, 1),
                y=metric_name,
                series=_get_dimension_name(ast, 0),
            )
        # Both date or neither date → fall through to table

    # Rule 4: Fallback to table for complex cases
    # - More than 2 dimensions
    # - 2 dimensions but both/neither are dates
    # - Multiple metrics (v1 limitation)
    return VisualizationSpec(type=VisualizationType.TABLE)


# Backward compatibility alias
def infer_chart_type(query: str) -> str:
    """
    Legacy function - returns 'table' for backward compatibility.

    Use infer_visualization() instead for proper AST-based inference.
    """
    return "table"
