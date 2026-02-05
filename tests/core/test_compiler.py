"""
Tests for SQL Compiler.

Tests that QueryAST + JoinPlan compile into correct SQLAlchemy Select objects.
"""

import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Numeric, String, Table, Date

from packages.core.schema_registry.registry import get_default_registry
from packages.core.sql_ast.compiler import SQLCompileError, SQLCompiler
from packages.core.sql_ast.join_resolver import JoinPlan, JoinResolver, JoinStep
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
from packages.core.schema_registry.registry import JoinType


# -----------------------------
# Fixtures
# -----------------------------


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


# -----------------------------
# Helper to compile SQL string
# -----------------------------


def compile_to_sql(compiler: SQLCompiler, resolver: JoinResolver, query: QueryAST) -> str:
    """Helper to compile a query to SQL string."""
    join_plan = resolver.resolve(query)
    select_stmt = compiler.compile(query, join_plan)
    return str(select_stmt.compile(compile_kwargs={"literal_binds": True}))


# -----------------------------
# Basic Compilation Tests
# -----------------------------


class TestBasicCompilation:
    """Tests for basic query compilation."""

    def test_simple_sum_query(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Simple SUM query should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "sum(orders.quantity)" in sql.lower()
        assert "from orders" in sql.lower()
        assert "limit 50" in sql.lower()

    def test_count_query(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """COUNT query should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.COUNT, field="quantity")],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "count(orders.quantity)" in sql.lower()

    def test_avg_query(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """AVG query should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.AVG, field="unit_price")],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "avg(orders.unit_price)" in sql.lower()

    def test_min_max_query(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """MIN/MAX queries should compile correctly."""
        query = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.MIN, field="quantity"),
                Metric(function=AggregateFunction.MAX, field="quantity"),
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "min(orders.quantity)" in sql.lower()
        assert "max(orders.quantity)" in sql.lower()

    def test_count_distinct_query(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """COUNT_DISTINCT should compile to count(distinct(...))."""
        query = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.COUNT_DISTINCT, field="region")
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "count(distinct" in sql.lower()
        assert "orders.region" in sql.lower()


# -----------------------------
# Dimension Tests
# -----------------------------


class TestDimensions:
    """Tests for dimension (GROUP BY) compilation."""

    def test_single_dimension(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Single dimension should appear in SELECT and GROUP BY."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "orders.region" in sql.lower()
        assert "group by" in sql.lower()

    def test_multiple_dimensions(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Multiple dimensions should all appear in GROUP BY."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[
                Dimension(field="region"),
                Dimension(field="product_line"),
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "orders.region" in sql.lower()
        assert "products.product_line" in sql.lower()
        assert "group by" in sql.lower()

    def test_dimension_with_alias(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Dimension with alias should be labeled."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region", alias="sales_region")],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "sales_region" in sql.lower()


# -----------------------------
# Filter Tests
# -----------------------------


class TestFilters:
    """Tests for filter (WHERE) compilation."""

    def test_equals_filter(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Equals filter should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="region", operator=FilterOperator.EQ, value="APAC"),
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "where" in sql.lower()
        assert "orders.region = 'apac'" in sql.lower()

    def test_not_equals_filter(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Not equals filter should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="region", operator=FilterOperator.NOT_EQ, value="APAC"),
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "orders.region != 'apac'" in sql.lower() or "orders.region <> 'apac'" in sql.lower()

    def test_greater_than_filter(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Greater than filter should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="quantity", operator=FilterOperator.GT, value=10),
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "orders.quantity > 10" in sql.lower()

    def test_between_filter(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """BETWEEN filter should compile correctly."""
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
        sql = compile_to_sql(compiler, resolver, query)

        assert "between" in sql.lower()
        assert "2024-01-01" in sql
        assert "2024-12-31" in sql

    def test_in_filter(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """IN filter should compile correctly."""
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
        sql = compile_to_sql(compiler, resolver, query)

        assert "in" in sql.lower()
        assert "apac" in sql.lower()
        assert "emea" in sql.lower()

    def test_not_in_filter(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """NOT IN filter should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(
                    field="region",
                    operator=FilterOperator.NOT_IN,
                    value=["NA"],
                ),
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "not in" in sql.lower()

    def test_like_filter(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """LIKE filter should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="region", operator=FilterOperator.LIKE, value="AP%"),
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "like" in sql.lower()
        assert "ap%" in sql.lower()

    def test_is_null_filter(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """IS NULL filter should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="region", operator=FilterOperator.IS_NULL, value=None),
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "is null" in sql.lower()

    def test_is_not_null_filter(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """IS NOT NULL filter should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="region", operator=FilterOperator.IS_NOT_NULL, value=None),
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "is not null" in sql.lower()

    def test_multiple_filters(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Multiple filters should be combined with AND."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            filters=[
                Filter(field="region", operator=FilterOperator.EQ, value="APAC"),
                Filter(field="quantity", operator=FilterOperator.GT, value=5),
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "and" in sql.lower()


# -----------------------------
# Join Tests
# -----------------------------


class TestJoins:
    """Tests for JOIN compilation."""

    def test_single_join(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Single join should be compiled correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="product_line")],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "join" in sql.lower()
        assert "products" in sql.lower()
        assert "product_id" in sql.lower()

    def test_multiple_joins(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Multiple joins should be compiled correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[
                Dimension(field="product_line"),
                Dimension(field="segment"),
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "products" in sql.lower()
        assert "customers" in sql.lower()


# -----------------------------
# Order By Tests
# -----------------------------


class TestOrderBy:
    """Tests for ORDER BY compilation."""

    def test_order_by_desc(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """ORDER BY DESC should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            order_by=[OrderBy(field="quantity", direction=OrderDirection.DESC)],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "order by" in sql.lower()
        assert "desc" in sql.lower()

    def test_order_by_asc(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """ORDER BY ASC should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            order_by=[OrderBy(field="quantity", direction=OrderDirection.ASC)],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "order by" in sql.lower()
        assert "asc" in sql.lower()

    def test_order_by_dimension(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """ORDER BY on dimension should work."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            dimensions=[Dimension(field="region")],
            order_by=[OrderBy(field="region", direction=OrderDirection.ASC)],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "order by" in sql.lower()
        assert "region" in sql.lower()


# -----------------------------
# Derived Metric Tests
# -----------------------------


class TestDerivedMetrics:
    """Tests for derived metric compilation."""

    def test_revenue_derived_metric(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Revenue (quantity * unit_price) should compile correctly."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="revenue")],
        )
        sql = compile_to_sql(compiler, resolver, query)

        # Should have multiplication in the query
        assert "quantity" in sql.lower()
        assert "unit_price" in sql.lower()
        assert "*" in sql or "×" in sql  # multiplication operator

    def test_revenue_with_alias(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Revenue with alias should be labeled correctly."""
        query = QueryAST(
            metrics=[
                Metric(
                    function=AggregateFunction.SUM,
                    field="revenue",
                    alias="total_revenue",
                )
            ],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "total_revenue" in sql.lower()


# -----------------------------
# Limit Tests
# -----------------------------


class TestLimit:
    """Tests for LIMIT compilation."""

    def test_default_limit(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Default limit of 50 should be applied."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "limit 50" in sql.lower()

    def test_custom_limit(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Custom limit should be applied."""
        query = QueryAST(
            metrics=[Metric(function=AggregateFunction.SUM, field="quantity")],
            limit=100,
        )
        sql = compile_to_sql(compiler, resolver, query)

        assert "limit 100" in sql.lower()


# -----------------------------
# Full Query Tests
# -----------------------------


class TestFullQueries:
    """Tests for complete, realistic queries."""

    def test_revenue_by_region_q1(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Full query: Revenue by region for Q1 2024."""
        query = QueryAST(
            metrics=[
                Metric(
                    function=AggregateFunction.SUM,
                    field="revenue",
                    alias="total_revenue",
                )
            ],
            dimensions=[Dimension(field="region")],
            filters=[
                Filter(
                    field="order_date",
                    operator=FilterOperator.BETWEEN,
                    value=["2024-01-01", "2024-03-31"],
                ),
            ],
            order_by=[OrderBy(field="total_revenue", direction=OrderDirection.DESC)],
            limit=10,
        )
        sql = compile_to_sql(compiler, resolver, query)

        # Check all components
        assert "sum(" in sql.lower()
        assert "quantity" in sql.lower()
        assert "unit_price" in sql.lower()
        assert "region" in sql.lower()
        assert "between" in sql.lower()
        assert "group by" in sql.lower()
        assert "order by" in sql.lower()
        assert "desc" in sql.lower()
        assert "limit 10" in sql.lower()

    def test_sales_by_product_and_segment(
        self, compiler: SQLCompiler, resolver: JoinResolver
    ) -> None:
        """Full query: Sales by product line and customer segment."""
        query = QueryAST(
            metrics=[
                Metric(function=AggregateFunction.SUM, field="quantity"),
                Metric(
                    function=AggregateFunction.SUM,
                    field="revenue",
                    alias="revenue",
                ),
            ],
            dimensions=[
                Dimension(field="product_line"),
                Dimension(field="segment"),
            ],
            order_by=[OrderBy(field="revenue", direction=OrderDirection.DESC)],
        )
        sql = compile_to_sql(compiler, resolver, query)

        # Check joins
        assert "products" in sql.lower()
        assert "customers" in sql.lower()
        # Check dimensions
        assert "product_line" in sql.lower()
        assert "segment" in sql.lower()
