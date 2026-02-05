"""
Join Resolver for ClarityQL.

Determines required tables and join steps for a given AST
using the schema registry.
"""

from dataclasses import dataclass

from packages.core.schema_registry.registry import (
    JoinType,
    SchemaRegistry,
    get_default_registry,
)
from packages.core.sql_ast.models import QueryAST


# -----------------------------
# Data structures
# -----------------------------


@dataclass(frozen=True)
class JoinStep:
    """Represents a single join operation."""

    left_table: str
    right_table: str
    left_key: str
    right_key: str
    join_type: JoinType = JoinType.LEFT


@dataclass(frozen=True)
class JoinPlan:
    """
    Complete join plan for a query.

    Contains the base table and ordered list of joins to execute.
    """

    base_table: str
    joins: tuple[JoinStep, ...]  # Use tuple for immutability


# -----------------------------
# Errors
# -----------------------------


class JoinResolutionError(Exception):
    """Raised when joins cannot be resolved for a query."""

    pass


# -----------------------------
# Resolver
# -----------------------------


class JoinResolver:
    """
    Resolves the required joins for a QueryAST.

    Uses the schema registry to determine which tables are needed
    and how to join them.
    """

    def __init__(self, registry: SchemaRegistry | None = None):
        """
        Initialize the resolver.

        Args:
            registry: Schema registry to use for lookups.
                     Uses default registry if not provided.
        """
        self._registry = registry or get_default_registry()

    def resolve(self, ast: QueryAST) -> JoinPlan:
        """
        Given a validated AST, determine the base table and required join steps.

        Args:
            ast: The QueryAST to resolve joins for.

        Returns:
            JoinPlan with base table and join steps.

        Raises:
            JoinResolutionError: If joins cannot be resolved.
        """
        required_tables = self._collect_required_tables(ast)
        base_table = self._determine_base_table(ast)

        joins: list[JoinStep] = []

        for table in required_tables:
            if table == base_table:
                continue

            join = self._find_join(base_table, table)
            if join is None:
                raise JoinResolutionError(
                    f"No join path found from '{base_table}' to '{table}'"
                )

            joins.append(join)

        return JoinPlan(base_table=base_table, joins=tuple(joins))

    # -------------------------
    # Helpers
    # -------------------------

    def _collect_required_tables(self, ast: QueryAST) -> set[str]:
        """Collect all tables required by the query."""
        tables: set[str] = set()

        # Collect from metrics
        for metric in ast.metrics:
            table = self._field_to_table(metric.field)
            tables.add(table)

        # Collect from dimensions
        for dim in ast.dimensions:
            table = self._field_to_table(dim.field)
            tables.add(table)

        # Collect from filters
        for f in ast.filters:
            table = self._field_to_table(f.field)
            tables.add(table)

        return tables

    def _determine_base_table(self, ast: QueryAST) -> str:
        """
        Determine the base (driving) table for the query.

        Strategy: Use the table of the first metric, as metrics
        are typically the primary focus of analytics queries.
        """
        return self._field_to_table(ast.metrics[0].field)

    def _field_to_table(self, field_name: str) -> str:
        """Resolve a field name to its source table."""
        # Check if it's a derived metric
        derived = self._registry.get_derived_metric(field_name)
        if derived is not None:
            return derived.base_table

        # Check regular fields
        table = self._registry.get_field_table(field_name)
        if table is not None:
            return table

        raise JoinResolutionError(
            f"Cannot resolve table for field '{field_name}'"
        )

    def _find_join(self, base_table: str, target_table: str) -> JoinStep | None:
        """
        Find a join between base table and target table.

        Currently supports direct joins only. Returns None if no
        direct join exists.
        """
        join_meta = self._registry.get_join(base_table, target_table)

        if join_meta is None:
            return None

        # Determine join direction (registry stores bidirectionally)
        if join_meta.left_table == base_table:
            return JoinStep(
                left_table=join_meta.left_table,
                right_table=join_meta.right_table,
                left_key=join_meta.left_key,
                right_key=join_meta.right_key,
                join_type=join_meta.join_type,
            )
        else:
            # Reverse the join direction
            return JoinStep(
                left_table=join_meta.right_table,
                right_table=join_meta.left_table,
                left_key=join_meta.right_key,
                right_key=join_meta.left_key,
                join_type=join_meta.join_type,
            )
