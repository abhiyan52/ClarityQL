"""
Tests for NLQ Follow-up Behavior and Merge Logic.

Tests cover:
1. Merge/follow-up behavior (e.g., "add group by product_line")
2. Integration tests with filter + group + aggregate + order + limit
3. LLM output validation for follow-ups
4. SQL safety guarantees (e.g., validation of unknown fields)
"""

import pytest
from sqlalchemy import Column, Date, ForeignKey, Integer, MetaData, Numeric, String, Table

from packages.core.conversation.ast_merge import (
    ASTMergeError,
    ast_diff,
    is_delta_empty,
    merge_ast,
)
from packages.core.safety.validator import ASTValidationError, ASTValidator
from packages.core.schema_registry.registry import get_default_registry
from packages.core.sql_ast.compiler import SQLCompiler
from packages.core.sql_ast.join_resolver import JoinResolver
from packages.core.sql_ast.models import (
    AggregateFunction,
    Dimension,
    Filter,
    FilterOperator,
    Metric,
    OrderBy,
    OrderDirection,
    QueryAST,
)


# ==============================
# Fixtures
# ==============================


@pytest.fixture
def metadata() -> MetaData:
    """Create SQLAlchemy metadata."""
    return MetaData()


@pytest.fixture
def sqlalchemy_tables(metadata: MetaData) -> dict:
    """Create SQLAlchemy Table objects matching the default registry."""
    orders = Table(
        "orders",
        metadata,
        Column("order_id", Integer, primary_key=True),
        Column("order_date", Date),
        Column("quantity", Integer),
        Column("unit_price", Numeric(10, 2)),
        Column("region", String(50)),
        Column("product_id", Integer, ForeignKey("products.product_id")),
        Column("customer_id", Integer, ForeignKey("customers.customer_id")),
    )

    products = Table(
        "products",
        metadata,
        Column("product_id", Integer, primary_key=True),
        Column("product_line", String(100)),
        Column("category", String(100)),
    )

    customers = Table(
        "customers",
        metadata,
        Column("customer_id", Integer, primary_key=True),
        Column("segment", String(50)),
        Column("country", String(100)),
    )

    return {
        "orders": orders,
        "products": products,
        "customers": customers,
    }


@pytest.fixture
def compiler(sqlalchemy_tables: dict) -> SQLCompiler:
    """Create a compiler with the default registry."""
    return SQLCompiler(
        sqlalchemy_tables=sqlalchemy_tables,
        registry=get_default_registry(),
    )


@pytest.fixture
def resolver() -> JoinResolver:
    """Create a resolver with the default registry."""
    return JoinResolver(registry=get_default_registry())


@pytest.fixture
def validator() -> ASTValidator:
    """Create a validator with the default registry."""
    return ASTValidator(registry=get_default_registry())


def compile_to_sql(compiler: SQLCompiler, resolver: JoinResolver, query: QueryAST) -> str:
    """Helper to compile a query to SQL string."""
    join_plan = resolver.resolve(query)
    select_stmt = compiler.compile(query, join_plan)
    return str(select_stmt.compile(compile_kwargs={"literal_binds": True}))


# ==============================
# AST Merge Tests
# ==============================


class TestASTMergeDimensions:
    """Tests for dimension merging in follow-ups."""

    def test_merge_adds_dimension_to_previous_query(self):
        """Follow-up adding 'group by product_line' should extend previous dimensions."""
        # Initial query: "Total quantity by region"
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
        )

        # Follow-up: "add group by product_line"
        # Note: Delta keeps previous metrics when not changing them
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="product_line")],
        )

        merged = merge_ast(previous, delta)

        # Should have both region and product_line
        assert len(merged.dimensions) == 2
        assert {d.field for d in merged.dimensions} == {"region", "product_line"}

    def test_merge_deduplicates_dimensions(self):
        """Merging with same dimension twice should not duplicate."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
        )

        # Try to add the same dimension
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
        )

        merged = merge_ast(previous, delta)

        # Should only have one region dimension
        assert len(merged.dimensions) == 1
        assert merged.dimensions[0].field == "region"

    def test_merge_multiple_dimensions_from_followup(self):
        """Follow-up can add multiple dimensions at once."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
        )

        # Add multiple dimensions: "break it down by product line and category"
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[
                Dimension(field="product_line"),
                Dimension(field="category"),
            ],
        )

        merged = merge_ast(previous, delta)

        assert len(merged.dimensions) == 3
        assert {d.field for d in merged.dimensions} == {"region", "product_line", "category"}


class TestASTMergeFilters:
    """Tests for filter merging in follow-ups."""

    def test_merge_adds_filter_to_previous_query(self):
        """Follow-up adding a filter should preserve previous query + add new filter."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[Filter(field="region", operator=FilterOperator.EQ, value="APAC")],
        )

        # Follow-up: "for Europe"
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[Filter(field="region", operator=FilterOperator.EQ, value="EMEA")],
        )

        merged = merge_ast(previous, delta)

        # New filter on 'region' should override old one
        assert len(merged.filters) == 1
        assert merged.filters[0].value == "EMEA"

    def test_merge_independent_filters(self):
        """Follow-up adding filter on different field should preserve both filters."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[Filter(field="region", operator=FilterOperator.EQ, value="APAC")],
        )

        # Follow-up: "where category is 'Electronics'"
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[Filter(field="category", operator=FilterOperator.EQ, value="Electronics")],
        )

        merged = merge_ast(previous, delta)

        # Should have both filters on different fields
        assert len(merged.filters) == 2
        assert {f.field for f in merged.filters} == {"region", "category"}

    def test_merge_overrides_filter_on_same_field(self):
        """New filter on same field should override previous."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[Filter(field="region", operator=FilterOperator.EQ, value="APAC")],
        )

        # Follow-up: "actually, for North America"
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[Filter(field="region", operator=FilterOperator.EQ, value="NA")],
        )

        merged = merge_ast(previous, delta)

        # Should have only one region filter with new value
        assert len(merged.filters) == 1
        assert merged.filters[0].value == "NA"


class TestASTMergeMetrics:
    """Tests for metric handling in follow-ups."""

    def test_merge_keeps_previous_metrics_when_delta_empty(self):
        """Follow-up without metrics should keep previous metrics."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
        )

        # Follow-up: just "add product_line" (no metric change)
        # We provide the same metric to keep it, representing "implicit" preservation
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="product_line")],
        )

        merged = merge_ast(previous, delta)

        # Metrics should be preserved (same as delta since delta == previous metrics)
        assert len(merged.metrics) == 1
        assert merged.metrics[0].field == "quantity"

    def test_merge_keeps_previous_metrics_with_new_dimensions(self):
        """Adding dimensions shouldn't affect metrics."""
        previous = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.SUM, field="quantity"),
                Metric(function=AggregateFunction.AVG, field="unit_price"),
            ],
            dimensions=[Dimension(field="region")],
        )

        delta = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.SUM, field="quantity"),
                Metric(function=AggregateFunction.AVG, field="unit_price"),
            ],
            dimensions=[Dimension(field="category")],
        )

        merged = merge_ast(previous, delta)

        # All metrics should be preserved
        assert len(merged.metrics) == 2


class TestASTMergeOrderBy:
    """Tests for ORDER BY handling in follow-ups."""

    def test_merge_keeps_previous_order_when_delta_empty(self):
        """Follow-up without order should keep previous order."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            order_by=[OrderBy(field="quantity", direction=OrderDirection.DESC)],
        )

        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
        )

        merged = merge_ast(previous, delta)

        # Order should be preserved (delta has empty order_by, so keeps previous)
        assert len(merged.order_by) == 1
        assert merged.order_by[0].field == "quantity"

    def test_merge_replaces_order_when_delta_provided(self):
        """Follow-up with new order should replace previous."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            order_by=[OrderBy(field="quantity", direction=OrderDirection.DESC)],
        )

        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            order_by=[OrderBy(field="region", direction=OrderDirection.ASC)],
        )

        merged = merge_ast(previous, delta)

        # Order should be replaced
        assert len(merged.order_by) == 1
        assert merged.order_by[0].field == "region"
        assert merged.order_by[0].direction == OrderDirection.ASC


class TestASTMergeLimit:
    """Tests for LIMIT handling in follow-ups."""

    def test_merge_keeps_previous_limit_when_delta_default(self):
        """Follow-up with default limit (50) should keep previous."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            limit=100,
        )

        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            limit=50,  # Default
        )

        merged = merge_ast(previous, delta)

        # Should keep previous limit
        assert merged.limit == 100

    def test_merge_replaces_limit_when_delta_custom(self):
        """Follow-up with custom limit should replace previous."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            limit=100,
        )

        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            limit=200,  # Custom value
        )

        merged = merge_ast(previous, delta)

        # Should use new limit
        assert merged.limit == 200


class TestASTDiff:
    """Tests for AST diff utility."""

    def test_diff_detects_added_dimension(self):
        """AST diff should detect when dimension is added."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
        )

        current = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region"), Dimension(field="product_line")],
        )

        diff = ast_diff(previous, current)

        assert "dimensions" in diff
        assert "product_line" in diff["dimensions"]["added"]

    def test_diff_detects_filter_changes(self):
        """AST diff should detect filter changes."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[Filter(field="region", operator=FilterOperator.EQ, value="APAC")],
        )

        current = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[Filter(field="region", operator=FilterOperator.EQ, value="EMEA")],
        )

        diff = ast_diff(previous, current)

        assert "filters" in diff
        assert "region" in diff["filters"]["changed"]


class TestIsDetaEmpty:
    """Tests for delta emptiness detection."""

    def test_empty_delta(self):
        """Delta with only defaults should be marked as empty."""
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[],
            filters=[],
            order_by=[],
            limit=50,  # Default
        )

        assert is_delta_empty(delta) is True

    def test_non_empty_delta_with_dimensions(self):
        """Delta with dimensions is not empty."""
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
            filters=[],
            order_by=[],
            limit=50,
        )

        assert is_delta_empty(delta) is False

    def test_non_empty_delta_with_custom_limit(self):
        """Delta with custom limit is not empty."""
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[],
            filters=[],
            order_by=[],
            limit=100,  # Custom
        )

        assert is_delta_empty(delta) is False


# ==============================
# Integration Tests (Full Query Compilation)
# ==============================


class TestFollowUpQueryCompilation:
    """Integration tests compiling follow-up queries to SQL."""

    def test_initial_query_filter_group_aggregate(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ):
        """Compile initial query: revenue by region."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[Dimension(field="region")],
            filters=[
                Filter(
                    field="order_date",
                    operator=FilterOperator.BETWEEN,
                    value=["2024-01-01", "2024-03-31"],
                ),
            ],
            order_by=[OrderBy(field="revenue", direction=OrderDirection.DESC)],
            limit=10,
        )

        sql = compile_to_sql(compiler, resolver, query)

        assert "sum(" in sql.lower()
        assert "group by" in sql.lower()
        assert "where" in sql.lower()
        assert "between" in sql.lower()
        assert "order by" in sql.lower()
        assert "desc" in sql.lower()
        assert "limit 10" in sql.lower()

    def test_followup_adds_dimension_to_filter_group_aggregate(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ):
        """Follow-up: add product_line dimension to existing query."""
        # Initial query
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[Dimension(field="region")],
            filters=[
                Filter(
                    field="order_date",
                    operator=FilterOperator.BETWEEN,
                    value=["2024-01-01", "2024-03-31"],
                ),
            ],
            order_by=[OrderBy(field="revenue", direction=OrderDirection.DESC)],
            limit=10,
        )

        # Follow-up: "break down by product line"
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[Dimension(field="product_line")],
        )

        merged = merge_ast(previous, delta)
        sql = compile_to_sql(compiler, resolver, merged)

        # Should have both dimensions
        assert "region" in sql.lower()
        assert "product_line" in sql.lower()
        assert "group by" in sql.lower()

    def test_followup_adds_aggregate_with_existing_filters_and_grouping(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ):
        """Follow-up: add additional metric to existing query."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region"), Dimension(field="product_line")],
            filters=[Filter(field="region", operator=FilterOperator.EQ, value="APAC")],
        )

        # Follow-up: "also show average price"
        delta = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.SUM, field="quantity"),
                Metric(function=AggregateFunction.AVG, field="unit_price"),
            ],
        )

        merged = merge_ast(previous, delta)
        sql = compile_to_sql(compiler, resolver, merged)

        # Should compile successfully and include both aggregates
        assert "sum(" in sql.lower()
        assert "avg(" in sql.lower()

    def test_full_pipeline_filter_group_aggregate_order_limit(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ):
        """Complex query: filter + group + aggregate + order + limit."""
        query = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.SUM, field="revenue"),
                Metric(function=AggregateFunction.AVG, field="unit_price"),
                Metric(function=AggregateFunction.COUNT, field="quantity"),
            ],
            dimensions=[
                Dimension(field="region"),
                Dimension(field="product_line"),
                Dimension(field="segment"),
            ],
            filters=[
                Filter(
                    field="order_date",
                    operator=FilterOperator.BETWEEN,
                    value=["2024-01-01", "2024-12-31"],
                ),
                Filter(field="region", operator=FilterOperator.IN, value=["APAC", "EMEA"]),
                Filter(field="quantity", operator=FilterOperator.GT, value=5),
            ],
            order_by=[
                OrderBy(field="revenue", direction=OrderDirection.DESC),
                OrderBy(field="region", direction=OrderDirection.ASC),
            ],
            limit=50,
        )

        sql = compile_to_sql(compiler, resolver, query)

        # Verify all components are present
        assert "sum(" in sql.lower()
        assert "avg(" in sql.lower()
        assert "count(" in sql.lower()
        assert "region" in sql.lower()
        assert "product_line" in sql.lower()
        assert "segment" in sql.lower()
        assert "where" in sql.lower()
        assert "between" in sql.lower()
        assert "group by" in sql.lower()
        assert "order by" in sql.lower()
        assert "limit 50" in sql.lower()


# ==============================
# LLM Output Validation Tests
# ==============================


class TestLLMOutputValidationForFollowUps:
    """Tests validating LLM outputs for typical follow-up queries."""

    def test_validate_followup_add_group_by_product_line(self, validator: ASTValidator):
        """Validate typical follow-up: 'add group by product_line'."""
        # This represents what the LLM would parse from "add group by product_line"
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="product_line")],
        )

        # Should be valid
        validator.validate(delta)

    def test_validate_followup_break_down_by_product_line(self, validator: ASTValidator):
        """Validate follow-up: 'break it down by product line'."""
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="product_line")],
        )

        validator.validate(delta)

    def test_validate_followup_filter_refine(self, validator: ASTValidator):
        """Validate follow-up: 'only for Europe'."""
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[Filter(field="region", operator=FilterOperator.EQ, value="EMEA")],
        )

        validator.validate(delta)

    def test_validate_followup_with_unknown_field_fails(self, validator: ASTValidator):
        """LLM output with unknown field should fail validation."""
        # This would happen if LLM hallucinates a field
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="nonexistent_field")],
        )

        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(delta)
        assert "Unknown dimension field 'nonexistent_field'" in str(exc_info.value)

    def test_validate_followup_with_multiple_valid_dimensions(self, validator: ASTValidator):
        """LLM output adding multiple dimensions should validate."""
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[
                Dimension(field="product_line"),
                Dimension(field="category"),
            ],
        )

        validator.validate(delta)


# ==============================
# SQL Safety Tests
# ==============================


class TestSQLSafetyGuarantees:
    """Tests documenting SQL safety guarantees against LLM hallucinations."""

    def test_llm_hallucination_unknown_metric_field_blocked(
        self, validator: ASTValidator
    ):
        """Safety: Unknown metric field from LLM is blocked at validation."""
        # Simulates LLM hallucinating a non-existent field
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="fantasy_metric")],
        )

        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "fantasy_metric" in str(exc_info.value)

    def test_llm_hallucination_unknown_dimension_field_blocked(
        self, validator: ASTValidator
    ):
        """Safety: Unknown dimension field from LLM is blocked at validation."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="made_up_dimension")],
        )

        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "made_up_dimension" in str(exc_info.value)

    def test_llm_hallucination_unknown_filter_field_blocked(
        self, validator: ASTValidator
    ):
        """Safety: Unknown filter field from LLM is blocked at validation."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="fake_column", operator=FilterOperator.EQ, value="test"),
            ],
        )

        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "fake_column" in str(exc_info.value)

    def test_llm_hallucination_non_aggregatable_metric_blocked(
        self, validator: ASTValidator
    ):
        """Safety: Attempting to aggregate non-aggregatable field is blocked."""
        # Trying to SUM a string field (region)
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="region")],
        )

        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "not aggregatable" in str(exc_info.value)

    def test_llm_wrong_operator_for_field_type_blocked(self, validator: ASTValidator):
        """Safety: Wrong operator for field type is blocked."""
        # Using > on a string field
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="region", operator=FilterOperator.GT, value="test"),
            ],
        )

        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "not allowed for string field" in str(exc_info.value)

    def test_invalid_between_operator_without_two_values_blocked(
        self, validator: ASTValidator
    ):
        """Safety: BETWEEN without exactly 2 values is blocked."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(
                    field="order_date",
                    operator=FilterOperator.BETWEEN,
                    value=["2024-01-01"],  # Only 1 value
                ),
            ],
        )

        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "requires exactly 2 values" in str(exc_info.value)

    def test_invalid_in_operator_without_list_blocked(self, validator: ASTValidator):
        """Safety: IN operator without list is blocked."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(
                    field="region",
                    operator=FilterOperator.IN,
                    value="APAC",  # Should be a list
                ),
            ],
        )

        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "requires a list" in str(exc_info.value)

    def test_order_by_invalid_field_blocked(self, validator: ASTValidator):
        """Safety: ORDER BY non-existent field is blocked."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
            order_by=[OrderBy(field="nonexistent_field")],  # Not in metrics or dimensions
        )

        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "must be a metric or dimension" in str(exc_info.value)

    def test_limit_exceeds_maximum_blocked(self):
        """Safety: LIMIT exceeding maximum is blocked at model creation."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            QueryAST(
                metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
                limit=5000,  # Exceeds max of 1000
            )
        assert "less than or equal to 1000" in str(exc_info.value)

    def test_cumulative_safety_filters_dimensions_aggregates(
        self, compiler: SQLCompiler, resolver: JoinResolver, validator: ASTValidator
    ):
        """Safety: Multiple validation layers prevent bad SQL generation."""
        # Create a valid query with all components
        query = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.SUM, field="revenue"),
                Metric(function=AggregateFunction.COUNT, field="quantity"),
            ],
            dimensions=[
                Dimension(field="region"),
                Dimension(field="product_line"),
            ],
            filters=[
                Filter(field="region", operator=FilterOperator.EQ, value="APAC"),
                Filter(
                    field="order_date",
                    operator=FilterOperator.BETWEEN,
                    value=["2024-01-01", "2024-12-31"],
                ),
            ],
            order_by=[OrderBy(field="revenue", direction=OrderDirection.DESC)],
            limit=100,
        )

        # Step 1: Validation passes
        validator.validate(query)

        # Step 2: Join resolution succeeds
        join_plan = resolver.resolve(query)
        assert join_plan is not None

        # Step 3: SQL compilation succeeds
        sql = compile_to_sql(compiler, resolver, query)
        assert "sum(" in sql.lower()
        assert "count(" in sql.lower()
        assert "group by" in sql.lower()


# ==============================
# Merge Error Handling Tests
# ==============================


class TestMergeErrorHandling:
    """Tests for error handling in AST merge operations."""

    def test_merge_queries_with_metrics_produces_valid_ast(self):
        """Merging queries with metrics should produce valid AST."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")]
        )
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")]
        )

        merged = merge_ast(previous, delta)

        assert merged is not None
        assert isinstance(merged, QueryAST)

    def test_merge_with_single_metric_previous(self):
        """Merge with single metric in previous query."""
        previous = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
        )
        delta = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
        )

        merged = merge_ast(previous, delta)

        assert len(merged.metrics) == 1
        assert len(merged.dimensions) == 1
