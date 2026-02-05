"""
Tests for Join Resolver.

Tests that join plans are correctly generated for QueryAST objects.
"""

import pytest

from packages.core.schema_registry.registry import get_default_registry, JoinType
from packages.core.sql_ast.join_resolver import (
    JoinPlan,
    JoinResolutionError,
    JoinResolver,
    JoinStep,
)
from packages.core.sql_ast.models import (
    AggregateFunction,
    Dimension,
    Filter,
    FilterOperator,
    Metric,
    QueryAST,
)


# -----------------------------
# Fixtures
# -----------------------------


@pytest.fixture
def resolver() -> JoinResolver:
    """Create a resolver with the default registry."""
    return JoinResolver(registry=get_default_registry())


# -----------------------------
# Single Table Tests
# -----------------------------


class TestSingleTableQueries:
    """Tests for queries that only need one table."""

    def test_single_table_no_joins(self, resolver: JoinResolver) -> None:
        """Query using only orders table needs no joins."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
        )
        plan = resolver.resolve(query)

        assert plan.base_table == "orders"
        assert plan.joins == ()

    def test_derived_metric_single_table(self, resolver: JoinResolver) -> None:
        """Derived metric (revenue) should resolve to its base table."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
        )
        plan = resolver.resolve(query)

        assert plan.base_table == "orders"
        assert plan.joins == ()

    def test_products_table_only(self, resolver: JoinResolver) -> None:
        """Query using only products table."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.COUNT, field="product_line")],
            dimensions=[Dimension(field="category")],
        )
        plan = resolver.resolve(query)

        assert plan.base_table == "products"
        assert plan.joins == ()


# -----------------------------
# Two Table Join Tests
# -----------------------------


class TestTwoTableJoins:
    """Tests for queries requiring joins between two tables."""

    def test_orders_to_products_join(self, resolver: JoinResolver) -> None:
        """Query with orders metric and products dimension needs join."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="product_line")],
        )
        plan = resolver.resolve(query)

        assert plan.base_table == "orders"
        assert len(plan.joins) == 1

        join = plan.joins[0]
        assert join.left_table == "orders"
        assert join.right_table == "products"
        assert join.left_key == "product_id"
        assert join.right_key == "product_id"
        assert join.join_type == JoinType.LEFT

    def test_orders_to_customers_join(self, resolver: JoinResolver) -> None:
        """Query with orders metric and customers dimension needs join."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[Dimension(field="segment")],
        )
        plan = resolver.resolve(query)

        assert plan.base_table == "orders"
        assert len(plan.joins) == 1

        join = plan.joins[0]
        assert join.left_table == "orders"
        assert join.right_table == "customers"
        assert join.left_key == "customer_id"
        assert join.right_key == "customer_id"

    def test_join_from_filter(self, resolver: JoinResolver) -> None:
        """Filter on different table should trigger join."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="category", operator=FilterOperator.EQ, value="Electronics")
            ],
        )
        plan = resolver.resolve(query)

        assert plan.base_table == "orders"
        assert len(plan.joins) == 1
        assert plan.joins[0].right_table == "products"


# -----------------------------
# Multi-Table Join Tests
# -----------------------------


class TestMultiTableJoins:
    """Tests for queries requiring multiple joins."""

    def test_orders_products_customers_joins(self, resolver: JoinResolver) -> None:
        """Query spanning all three tables needs multiple joins."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
            dimensions=[
                Dimension(field="product_line"),
                Dimension(field="segment"),
            ],
        )
        plan = resolver.resolve(query)

        assert plan.base_table == "orders"
        assert len(plan.joins) == 2

        joined_tables = {join.right_table for join in plan.joins}
        assert joined_tables == {"products", "customers"}

    def test_no_duplicate_joins(self, resolver: JoinResolver) -> None:
        """Multiple fields from same table should not create duplicate joins."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[
                Dimension(field="product_line"),
                Dimension(field="category"),  # Same table as product_line
            ],
        )
        plan = resolver.resolve(query)

        assert plan.base_table == "orders"
        assert len(plan.joins) == 1  # Only one join to products


# -----------------------------
# Error Cases
# -----------------------------


class TestJoinResolutionErrors:
    """Tests for error cases in join resolution."""

    def test_unknown_field_raises_error(self, resolver: JoinResolver) -> None:
        """Unknown field should raise JoinResolutionError."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="unknown_field")],
        )
        with pytest.raises(JoinResolutionError) as exc_info:
            resolver.resolve(query)
        assert "Cannot resolve table for field 'unknown_field'" in str(exc_info.value)


# -----------------------------
# JoinPlan/JoinStep Tests
# -----------------------------


class TestJoinPlanImmutability:
    """Tests for JoinPlan and JoinStep data structures."""

    def test_join_plan_is_immutable(self, resolver: JoinResolver) -> None:
        """JoinPlan should be immutable (frozen dataclass with tuple)."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="product_line")],
        )
        plan = resolver.resolve(query)

        # JoinPlan is frozen
        with pytest.raises(AttributeError):
            plan.base_table = "other"  # type: ignore

        # Joins is a tuple (immutable)
        assert isinstance(plan.joins, tuple)

    def test_join_step_is_immutable(self, resolver: JoinResolver) -> None:
        """JoinStep should be immutable (frozen dataclass)."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="product_line")],
        )
        plan = resolver.resolve(query)
        join = plan.joins[0]

        with pytest.raises(AttributeError):
            join.left_table = "other"  # type: ignore


# -----------------------------
# Base Table Selection Tests
# -----------------------------


class TestBaseTableSelection:
    """Tests for base table determination logic."""

    def test_base_table_from_first_metric(self, resolver: JoinResolver) -> None:
        """Base table should be determined from first metric."""
        # First metric is from orders (revenue)
        query = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.SUM, field="revenue"),
                Metric(function=AggregateFunction.COUNT, field="product_line"),
            ],
        )
        plan = resolver.resolve(query)
        assert plan.base_table == "orders"

    def test_base_table_products_first(self, resolver: JoinResolver) -> None:
        """If first metric is from products, base table should be products."""
        query = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.COUNT, field="product_line"),
            ],
            dimensions=[Dimension(field="region")],
        )
        plan = resolver.resolve(query)

        # Base table is products (from first metric)
        assert plan.base_table == "products"
        # Need to join to orders for the region dimension
        assert len(plan.joins) == 1
