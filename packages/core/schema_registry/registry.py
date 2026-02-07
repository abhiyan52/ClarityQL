"""
Schema Registry for ClarityQL.

This module defines:
- Which semantic fields exist
- Where they live (tables / columns)
- How tables are joined
- Which derived metrics are available

This is the SINGLE source of truth for query compilation.
"""

from dataclasses import dataclass, field
from enum import Enum


# -----------------------------
# Field Types
# -----------------------------


class FieldType(str, Enum):
    """Supported field data types."""

    STRING = "string"
    NUMERIC = "numeric"
    DATE = "date"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"


class JoinType(str, Enum):
    """Supported SQL join types."""

    INNER = "inner"
    LEFT = "left"
    RIGHT = "right"
    FULL = "full"


# -----------------------------
# Field & Table Metadata
# -----------------------------


@dataclass(frozen=True)
class FieldMeta:
    """Metadata for a single field/column."""

    table: str  # physical table (e.g. "orders")
    column: str  # physical column (e.g. "region")
    field_type: FieldType  # data type
    description: str = ""  # human-readable description for LLM context
    aggregatable: bool = False  # can this field be used in SUM/AVG/etc?
    allowed_values: tuple[str, ...] | None = None  # for categorical fields
    date_trunc: str | None = None  # when grouping: "month", "quarter", "year" (PostgreSQL)


@dataclass(frozen=True)
class TableMeta:
    """Metadata for a database table."""

    name: str
    description: str = ""
    primary_key: str = "id"
    fields: dict[str, FieldMeta] = field(default_factory=dict)


# -----------------------------
# Join Metadata
# -----------------------------


@dataclass(frozen=True)
class JoinMeta:
    """Defines how two tables can be joined."""

    left_table: str
    right_table: str
    left_key: str
    right_key: str
    join_type: JoinType = JoinType.LEFT


# -----------------------------
# Derived Metrics
# -----------------------------


@dataclass(frozen=True)
class DerivedMetric:
    """A computed metric derived from base fields."""

    name: str
    base_table: str
    expression: str  # symbolic expression, NOT SQL (e.g. "quantity * unit_price")
    description: str = ""
    fields_used: tuple[str, ...] = ()  # fields this metric depends on


# -----------------------------
# Schema Registry Class
# -----------------------------


class SchemaRegistry:
    """
    Central registry for schema metadata.

    Provides lookup methods for fields, tables, joins, and derived metrics.
    """

    def __init__(
        self,
        tables: dict[str, TableMeta],
        joins: list[JoinMeta],
        derived_metrics: dict[str, DerivedMetric],
    ):
        self._tables = tables
        self._joins = joins
        self._derived_metrics = derived_metrics

        # Build field index for fast lookups
        self._field_index: dict[str, tuple[str, FieldMeta]] = {}
        for table_name, table in tables.items():
            for field_name, field_meta in table.fields.items():
                self._field_index[field_name] = (table_name, field_meta)

        # Build join graph for path finding
        self._join_graph: dict[str, dict[str, JoinMeta]] = {}
        for join in joins:
            if join.left_table not in self._join_graph:
                self._join_graph[join.left_table] = {}
            if join.right_table not in self._join_graph:
                self._join_graph[join.right_table] = {}
            self._join_graph[join.left_table][join.right_table] = join
            self._join_graph[join.right_table][join.left_table] = join

    # -------------------------
    # Lookup Methods
    # -------------------------

    def get_field(self, field_name: str) -> FieldMeta | None:
        """Get field metadata by semantic name."""
        result = self._field_index.get(field_name)
        return result[1] if result else None

    def get_field_table(self, field_name: str) -> str | None:
        """Get the table name that contains a field."""
        result = self._field_index.get(field_name)
        return result[0] if result else None

    def get_table(self, table_name: str) -> TableMeta | None:
        """Get table metadata by name."""
        return self._tables.get(table_name)

    def get_derived_metric(self, metric_name: str) -> DerivedMetric | None:
        """Get derived metric by name."""
        return self._derived_metrics.get(metric_name)

    def field_exists(self, field_name: str) -> bool:
        """Check if a field exists in the registry."""
        return field_name in self._field_index or field_name in self._derived_metrics

    def get_join(self, table_a: str, table_b: str) -> JoinMeta | None:
        """Get the join definition between two tables."""
        if table_a in self._join_graph:
            return self._join_graph[table_a].get(table_b)
        return None

    def get_required_tables(self, field_names: list[str]) -> set[str]:
        """Get all tables needed to satisfy a list of fields."""
        tables = set()
        for field_name in field_names:
            # Check regular fields
            if field_name in self._field_index:
                tables.add(self._field_index[field_name][0])
            # Check derived metrics
            elif field_name in self._derived_metrics:
                metric = self._derived_metrics[field_name]
                tables.add(metric.base_table)
        return tables

    def list_fields(self) -> list[str]:
        """List all available field names."""
        return list(self._field_index.keys())

    def list_derived_metrics(self) -> list[str]:
        """List all available derived metric names."""
        return list(self._derived_metrics.keys())

    def list_tables(self) -> list[str]:
        """List all available table names."""
        return list(self._tables.keys())


# -----------------------------
# Default Registry Definition
# -----------------------------

_DEFAULT_TABLES: dict[str, TableMeta] = {
    "orders": TableMeta(
        name="orders",
        description="Sales order records",
        primary_key="order_id",
        fields={
            "order_date": FieldMeta(
                table="orders",
                column="order_date",
                field_type=FieldType.DATE,
                description="Date when the order was placed",
            ),
            "order_month": FieldMeta(
                table="orders",
                column="order_date",
                field_type=FieldType.DATE,
                description="Month of the order (use for monthly trends)",
                date_trunc="month",
            ),
            "quantity": FieldMeta(
                table="orders",
                column="quantity",
                field_type=FieldType.NUMERIC,
                description="Number of units ordered",
                aggregatable=True,
            ),
            "unit_price": FieldMeta(
                table="orders",
                column="unit_price",
                field_type=FieldType.NUMERIC,
                description="Price per unit in dollars",
                aggregatable=True,
            ),
            "region": FieldMeta(
                table="orders",
                column="region",
                field_type=FieldType.STRING,
                description="Geographic sales region",
                allowed_values=("North America", "Europe", "APAC", "LATAM"),
            ),
        },
    ),
    "products": TableMeta(
        name="products",
        description="Product catalog",
        primary_key="product_id",
        fields={
            "product_line": FieldMeta(
                table="products",
                column="product_line",
                field_type=FieldType.STRING,
                description="Product line name",
                allowed_values=("Core", "Pro", "Enterprise"),
            ),
            "category": FieldMeta(
                table="products",
                column="category",
                field_type=FieldType.STRING,
                description="Product category",
                allowed_values=("Analytics", "Data Ops", "Finance", "Growth", "Security"),
            ),
        },
    ),
    "customers": TableMeta(
        name="customers",
        description="Customer information",
        primary_key="customer_id",
        fields={
            "segment": FieldMeta(
                table="customers",
                column="segment",
                field_type=FieldType.STRING,
                description="Customer segment",
                allowed_values=("Enterprise", "Mid-Market", "SMB"),
            ),
            "country": FieldMeta(
                table="customers",
                column="country",
                field_type=FieldType.STRING,
                description="Customer country",
            ),
        },
    ),
}

_DEFAULT_JOINS: list[JoinMeta] = [
    JoinMeta(
        left_table="orders",
        right_table="products",
        left_key="product_id",
        right_key="product_id",
    ),
    JoinMeta(
        left_table="orders",
        right_table="customers",
        left_key="customer_id",
        right_key="customer_id",
    ),
]

_DEFAULT_DERIVED_METRICS: dict[str, DerivedMetric] = {
    "revenue": DerivedMetric(
        name="revenue",
        base_table="orders",
        expression="quantity * unit_price",
        description="Total revenue (quantity × unit price)",
        fields_used=("quantity", "unit_price"),
    ),
}


def get_default_registry() -> SchemaRegistry:
    """Get the default schema registry instance."""
    return SchemaRegistry(
        tables=_DEFAULT_TABLES,
        joins=_DEFAULT_JOINS,
        derived_metrics=_DEFAULT_DERIVED_METRICS,
    )
