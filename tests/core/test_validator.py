"""
Tests for AST Validator.

Tests that QueryAST objects are correctly validated against the schema registry.
"""

import pytest
from pydantic import ValidationError

from packages.core.safety.validator import ASTValidationError, ASTValidator
from packages.core.schema_registry.registry import get_default_registry
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


# -----------------------------
# Fixtures
# -----------------------------


@pytest.fixture
def validator() -> ASTValidator:
    """Create a validator with the default registry."""
    return ASTValidator(registry=get_default_registry())


@pytest.fixture
def valid_query() -> QueryAST:
    """Create a valid query for testing."""
    return QueryAST(
        metrics=[
            Metric(function=AggregateFunction.SUM, field="revenue"),
        ],
        dimensions=[
            Dimension(field="region"),
        ],
        filters=[
            Filter(
                field="order_date",
                operator=FilterOperator.BETWEEN,
                value=["2024-01-01", "2024-03-31"],
            ),
        ],
        order_by=[
            OrderBy(field="revenue", direction=OrderDirection.DESC),
        ],
        limit=50,
    )


# -----------------------------
# Valid Query Tests
# -----------------------------


class TestValidQueries:
    """Tests for valid query scenarios."""

    def test_valid_simple_query(self, validator: ASTValidator) -> None:
        """A simple valid query should pass validation."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
        )
        validator.validate(query)  # Should not raise

    def test_valid_query_with_all_components(
        self, validator: ASTValidator, valid_query: QueryAST
    ) -> None:
        """A query with metrics, dimensions, filters, and order_by should pass."""
        validator.validate(valid_query)  # Should not raise

    def test_valid_derived_metric(self, validator: ASTValidator) -> None:
        """Derived metrics (like revenue) should be valid."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[Dimension(field="region")],
        )
        validator.validate(query)  # Should not raise

    def test_valid_multiple_metrics(self, validator: ASTValidator) -> None:
        """Multiple metrics in a query should be valid."""
        query = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.SUM, field="quantity"),
                Metric(function=AggregateFunction.AVG, field="unit_price"),
            ],
        )
        validator.validate(query)  # Should not raise

    def test_valid_multiple_dimensions(self, validator: ASTValidator) -> None:
        """Multiple dimensions should be valid."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[
                Dimension(field="region"),
                Dimension(field="category"),
            ],
        )
        validator.validate(query)  # Should not raise

    def test_valid_string_filter_with_eq(self, validator: ASTValidator) -> None:
        """String fields should accept = operator."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="region", operator=FilterOperator.EQ, value="APAC"),
            ],
        )
        validator.validate(query)  # Should not raise

    def test_valid_string_filter_with_in(self, validator: ASTValidator) -> None:
        """String fields should accept IN operator."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(
                    field="region",
                    operator=FilterOperator.IN,
                    value=["APAC", "EMEA"],
                ),
            ],
        )
        validator.validate(query)  # Should not raise

    def test_valid_string_filter_with_like(self, validator: ASTValidator) -> None:
        """String fields should accept LIKE operator."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="region", operator=FilterOperator.LIKE, value="AP%"),
            ],
        )
        validator.validate(query)  # Should not raise

    def test_valid_date_filter_with_between(self, validator: ASTValidator) -> None:
        """Date fields should accept BETWEEN operator."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(
                    field="order_date",
                    operator=FilterOperator.BETWEEN,
                    value=["2024-01-01", "2024-12-31"],
                ),
            ],
        )
        validator.validate(query)  # Should not raise

    def test_valid_date_filter_with_comparison(self, validator: ASTValidator) -> None:
        """Date fields should accept comparison operators."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(
                    field="order_date",
                    operator=FilterOperator.GTE,
                    value="2024-01-01",
                ),
            ],
        )
        validator.validate(query)  # Should not raise

    def test_valid_numeric_filter_with_comparison(
        self, validator: ASTValidator
    ) -> None:
        """Numeric fields should accept comparison operators."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.COUNT, field="quantity")],
            filters=[
                Filter(field="quantity", operator=FilterOperator.GT, value=10),
            ],
        )
        validator.validate(query)  # Should not raise


# -----------------------------
# Invalid Field Tests
# -----------------------------


class TestUnknownFields:
    """Tests for unknown/invalid field references."""

    def test_unknown_metric_field_raises_error(self, validator: ASTValidator) -> None:
        """Unknown metric field should raise ASTValidationError."""
        query = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.SUM, field="nonexistent_field"),
            ],
        )
        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "Unknown metric field 'nonexistent_field'" in str(exc_info.value)

    def test_unknown_dimension_field_raises_error(
        self, validator: ASTValidator
    ) -> None:
        """Unknown dimension field should raise ASTValidationError."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="unknown_dimension")],
        )
        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "Unknown dimension field 'unknown_dimension'" in str(exc_info.value)

    def test_unknown_filter_field_raises_error(self, validator: ASTValidator) -> None:
        """Unknown filter field should raise ASTValidationError."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="bad_field", operator=FilterOperator.EQ, value="test"),
            ],
        )
        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "Unknown filter field 'bad_field'" in str(exc_info.value)


# -----------------------------
# Aggregatable Field Tests
# -----------------------------


class TestAggregatableFields:
    """Tests for aggregatable field validation."""

    def test_non_aggregatable_field_in_metric_raises_error(
        self, validator: ASTValidator
    ) -> None:
        """Non-aggregatable fields cannot be used in metrics."""
        query = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.SUM, field="region"),  # string field
            ],
        )
        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "Field 'region' is not aggregatable" in str(exc_info.value)

    def test_aggregatable_field_in_metric_is_valid(
        self, validator: ASTValidator
    ) -> None:
        """Aggregatable fields can be used in metrics."""
        query = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.SUM, field="quantity"),
            ],
        )
        validator.validate(query)  # Should not raise


# -----------------------------
# Operator Validation Tests
# -----------------------------


class TestOperatorValidation:
    """Tests for operator type validation."""

    def test_string_field_rejects_gt_operator(self, validator: ASTValidator) -> None:
        """String fields should not accept > operator."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="region", operator=FilterOperator.GT, value="A"),
            ],
        )
        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "Operator '>' not allowed for string field 'region'" in str(
            exc_info.value
        )

    def test_string_field_rejects_between_operator(
        self, validator: ASTValidator
    ) -> None:
        """String fields should not accept BETWEEN operator."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(
                    field="region",
                    operator=FilterOperator.BETWEEN,
                    value=["A", "Z"],
                ),
            ],
        )
        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "not allowed for string field 'region'" in str(exc_info.value)

    def test_date_field_rejects_like_operator(self, validator: ASTValidator) -> None:
        """Date fields should not accept LIKE operator."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(
                    field="order_date",
                    operator=FilterOperator.LIKE,
                    value="2024%",
                ),
            ],
        )
        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "not allowed for date field 'order_date'" in str(exc_info.value)


# -----------------------------
# Filter Value Validation Tests
# -----------------------------


class TestFilterValueValidation:
    """Tests for filter value format validation."""

    def test_between_requires_two_values(self, validator: ASTValidator) -> None:
        """BETWEEN operator requires exactly 2 values."""
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
        assert "BETWEEN operator for 'order_date' requires exactly 2 values" in str(
            exc_info.value
        )

    def test_between_rejects_single_value(self, validator: ASTValidator) -> None:
        """BETWEEN operator should reject a single non-list value."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(
                    field="order_date",
                    operator=FilterOperator.BETWEEN,
                    value="2024-01-01",  # Single value, not a list
                ),
            ],
        )
        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "requires exactly 2 values" in str(exc_info.value)

    def test_in_requires_list(self, validator: ASTValidator) -> None:
        """IN operator requires a list of values."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(
                    field="region",
                    operator=FilterOperator.IN,
                    value="APAC",  # Single value, not a list
                ),
            ],
        )
        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "IN/NOT_IN operator for 'region' requires a list" in str(exc_info.value)

    def test_not_in_requires_list(self, validator: ASTValidator) -> None:
        """NOT_IN operator requires a list of values."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(
                    field="region",
                    operator=FilterOperator.NOT_IN,
                    value="APAC",  # Single value, not a list
                ),
            ],
        )
        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "IN/NOT_IN operator for 'region' requires a list" in str(exc_info.value)


# -----------------------------
# ORDER BY Validation Tests
# -----------------------------


class TestOrderByValidation:
    """Tests for ORDER BY field validation."""

    def test_order_by_field_not_in_select_raises_error(
        self, validator: ASTValidator
    ) -> None:
        """ORDER BY field must be a metric or dimension."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
            order_by=[OrderBy(field="category")],  # Not in metrics or dimensions
        )
        with pytest.raises(ASTValidationError) as exc_info:
            validator.validate(query)
        assert "ORDER BY field 'category' must be a metric or dimension" in str(
            exc_info.value
        )

    def test_order_by_metric_field_is_valid(self, validator: ASTValidator) -> None:
        """ORDER BY on a metric field should be valid."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            order_by=[OrderBy(field="quantity")],
        )
        validator.validate(query)  # Should not raise

    def test_order_by_dimension_field_is_valid(self, validator: ASTValidator) -> None:
        """ORDER BY on a dimension field should be valid."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
            order_by=[OrderBy(field="region")],
        )
        validator.validate(query)  # Should not raise

    def test_order_by_alias_is_valid(self, validator: ASTValidator) -> None:
        """ORDER BY on an aliased field should be valid."""
        query = QueryAST(
            metrics=[
                Metric(
                    function=AggregateFunction.SUM, field="quantity", alias="total_qty"
                )
            ],
            order_by=[OrderBy(field="total_qty")],
        )
        validator.validate(query)  # Should not raise


# -----------------------------
# Limit Validation Tests
# -----------------------------


class TestLimitValidation:
    """Tests for limit validation."""

    def test_limit_exceeds_maximum_raises_pydantic_error(self) -> None:
        """Limit over 1000 should raise Pydantic ValidationError at model creation."""
        with pytest.raises(ValidationError) as exc_info:
            QueryAST(
                metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
                limit=1001,
            )
        assert "less than or equal to 1000" in str(exc_info.value)

    def test_limit_below_minimum_raises_pydantic_error(self) -> None:
        """Limit below 1 should raise Pydantic ValidationError at model creation."""
        with pytest.raises(ValidationError) as exc_info:
            QueryAST(
                metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
                limit=0,
            )
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_limit_at_maximum_is_valid(self, validator: ASTValidator) -> None:
        """Limit of exactly 1000 should be valid."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            limit=1000,
        )
        validator.validate(query)  # Should not raise

    def test_limit_of_1_is_valid(self, validator: ASTValidator) -> None:
        """Limit of 1 should be valid."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            limit=1,
        )
        validator.validate(query)  # Should not raise
