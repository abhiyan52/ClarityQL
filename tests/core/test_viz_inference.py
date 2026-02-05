"""
Tests for visualization inference module.

These tests verify the deterministic rules for chart type selection
based on the QueryAST structure.
"""

import pytest

from packages.core.schema_registry.registry import (
    FieldMeta,
    FieldType,
    SchemaRegistry,
    TableMeta,
)
from packages.core.sql_ast.models import (
    AggregateFunction,
    Dimension,
    Metric,
    QueryAST,
)
from packages.core.viz_inference import (
    VisualizationSpec,
    VisualizationType,
    infer_visualization,
)


@pytest.fixture
def registry() -> SchemaRegistry:
    """Create a test schema registry with date and categorical fields."""
    tables = {
        "orders": TableMeta(
            name="orders",
            description="Sales orders",
            primary_key="order_id",
            fields={
                "order_date": FieldMeta(
                    table="orders",
                    column="order_date",
                    field_type=FieldType.DATE,
                    description="Order date",
                ),
                "region": FieldMeta(
                    table="orders",
                    column="region",
                    field_type=FieldType.STRING,
                    description="Sales region",
                ),
                "category": FieldMeta(
                    table="orders",
                    column="category",
                    field_type=FieldType.STRING,
                    description="Product category",
                ),
                "quantity": FieldMeta(
                    table="orders",
                    column="quantity",
                    field_type=FieldType.NUMERIC,
                    aggregatable=True,
                ),
                "revenue": FieldMeta(
                    table="orders",
                    column="revenue",
                    field_type=FieldType.NUMERIC,
                    aggregatable=True,
                ),
                "created_at": FieldMeta(
                    table="orders",
                    column="created_at",
                    field_type=FieldType.TIMESTAMP,
                    description="Creation timestamp",
                ),
            },
        ),
    }
    return SchemaRegistry(tables=tables, joins=[], derived_metrics={})


class TestRule1_KPI:
    """Rule 1: No dimensions, metrics only → KPI"""

    def test_single_metric_returns_kpi(self, registry: SchemaRegistry):
        """Single metric without dimensions should return KPI."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[],
        )

        result = infer_visualization(ast, registry)

        assert result.type == VisualizationType.KPI
        assert result.y == "sum_revenue"
        assert result.x is None
        assert result.series is None

    def test_multiple_metrics_returns_kpi(self, registry: SchemaRegistry):
        """Multiple metrics without dimensions should return KPI (uses first metric)."""
        ast = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.SUM, field="revenue"),
                Metric(function=AggregateFunction.COUNT, field="quantity"),
            ],
            dimensions=[],
        )

        result = infer_visualization(ast, registry)

        assert result.type == VisualizationType.KPI
        assert result.y == "sum_revenue"

    def test_metric_with_alias_uses_alias(self, registry: SchemaRegistry):
        """Metric with alias should use alias as y label."""
        ast = QueryAST(
            metrics=[
                Metric(
                    function=AggregateFunction.SUM,
                    field="revenue",
                    alias="total_revenue",
                )
            ],
            dimensions=[],
        )

        result = infer_visualization(ast, registry)

        assert result.type == VisualizationType.KPI
        assert result.y == "total_revenue"


class TestRule2_SingleDimension:
    """Rule 2: 1 dimension + metrics → bar (categorical) or line (date)"""

    def test_categorical_dimension_returns_bar(self, registry: SchemaRegistry):
        """Categorical dimension should return bar chart."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[Dimension(field="region")],
        )

        result = infer_visualization(ast, registry)

        assert result.type == VisualizationType.BAR
        assert result.x == "region"
        assert result.y == "sum_revenue"
        assert result.series is None

    def test_date_dimension_returns_line(self, registry: SchemaRegistry):
        """Date dimension should return line chart."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[Dimension(field="order_date")],
        )

        result = infer_visualization(ast, registry)

        assert result.type == VisualizationType.LINE
        assert result.x == "order_date"
        assert result.y == "sum_revenue"
        assert result.series is None

    def test_timestamp_dimension_returns_line(self, registry: SchemaRegistry):
        """Timestamp dimension should return line chart."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[Dimension(field="created_at")],
        )

        result = infer_visualization(ast, registry)

        assert result.type == VisualizationType.LINE
        assert result.x == "created_at"
        assert result.y == "sum_revenue"

    def test_dimension_with_alias_uses_alias(self, registry: SchemaRegistry):
        """Dimension with alias should use alias as x label."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[Dimension(field="region", alias="sales_region")],
        )

        result = infer_visualization(ast, registry)

        assert result.type == VisualizationType.BAR
        assert result.x == "sales_region"


class TestRule3_TwoDimensions:
    """Rule 3: 2 dimensions (one date + one categorical) → multi-line"""

    def test_date_first_categorical_second_returns_multiline(
        self, registry: SchemaRegistry
    ):
        """Date as first dimension, categorical as second → multi-line."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[
                Dimension(field="order_date"),
                Dimension(field="region"),
            ],
        )

        result = infer_visualization(ast, registry)

        assert result.type == VisualizationType.MULTI_LINE
        assert result.x == "order_date"  # Date is x-axis
        assert result.y == "sum_revenue"
        assert result.series == "region"  # Categorical is series

    def test_categorical_first_date_second_returns_multiline(
        self, registry: SchemaRegistry
    ):
        """Categorical as first dimension, date as second → multi-line."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[
                Dimension(field="region"),
                Dimension(field="order_date"),
            ],
        )

        result = infer_visualization(ast, registry)

        assert result.type == VisualizationType.MULTI_LINE
        assert result.x == "order_date"  # Date is x-axis
        assert result.y == "sum_revenue"
        assert result.series == "region"  # Categorical is series

    def test_two_categorical_dimensions_returns_table(
        self, registry: SchemaRegistry
    ):
        """Two categorical dimensions → table (not multi-line)."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[
                Dimension(field="region"),
                Dimension(field="category"),
            ],
        )

        result = infer_visualization(ast, registry)

        assert result.type == VisualizationType.TABLE

    def test_two_date_dimensions_returns_table(self, registry: SchemaRegistry):
        """Two date dimensions → table (not multi-line)."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[
                Dimension(field="order_date"),
                Dimension(field="created_at"),
            ],
        )

        result = infer_visualization(ast, registry)

        assert result.type == VisualizationType.TABLE


class TestRule4_Fallback:
    """Rule 4: Complex cases → table"""

    def test_three_dimensions_returns_table(self, registry: SchemaRegistry):
        """Three or more dimensions → table."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[
                Dimension(field="order_date"),
                Dimension(field="region"),
                Dimension(field="category"),
            ],
        )

        result = infer_visualization(ast, registry)

        assert result.type == VisualizationType.TABLE

    def test_unknown_field_returns_bar_as_categorical(
        self, registry: SchemaRegistry
    ):
        """Unknown field treated as categorical (string) → bar chart."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[Dimension(field="unknown_field")],
        )

        result = infer_visualization(ast, registry)

        # Unknown field is not recognized as date, so treated as categorical
        assert result.type == VisualizationType.BAR


class TestVisualizationSpecSerialization:
    """Test VisualizationSpec serialization."""

    def test_to_dict_bar_chart(self, registry: SchemaRegistry):
        """Test to_dict for bar chart."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[Dimension(field="region")],
        )

        result = infer_visualization(ast, registry)
        dict_result = result.to_dict()

        assert dict_result == {
            "type": "bar",
            "x": "region",
            "y": "sum_revenue",
            "series": None,
        }

    def test_to_dict_kpi(self, registry: SchemaRegistry):
        """Test to_dict for KPI."""
        ast = QueryAST(
            metrics=[
                Metric(
                    function=AggregateFunction.SUM,
                    field="revenue",
                    alias="total",
                )
            ],
            dimensions=[],
        )

        result = infer_visualization(ast, registry)
        dict_result = result.to_dict()

        assert dict_result == {
            "type": "kpi",
            "x": None,
            "y": "total",
            "series": None,
        }

    def test_to_dict_multiline(self, registry: SchemaRegistry):
        """Test to_dict for multi-line chart."""
        ast = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[
                Dimension(field="order_date"),
                Dimension(field="region"),
            ],
        )

        result = infer_visualization(ast, registry)
        dict_result = result.to_dict()

        assert dict_result == {
            "type": "multi-line",
            "x": "order_date",
            "y": "sum_revenue",
            "series": "region",
        }
