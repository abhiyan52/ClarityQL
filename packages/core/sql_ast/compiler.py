"""
SQLAlchemy Compiler for ClarityQL.

Transforms a validated QueryAST and JoinPlan into a SQLAlchemy Select object.
"""

from sqlalchemy import and_, func, literal_column, select
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from packages.core.schema_registry.registry import (
    DerivedMetric,
    JoinType,
    SchemaRegistry,
    get_default_registry,
)
from packages.core.sql_ast.join_resolver import JoinPlan, JoinStep
from packages.core.sql_ast.models import (
    AggregateFunction,
    Filter,
    FilterOperator,
    Metric,
    OrderBy,
    QueryAST,
)


# -----------------------------
# Errors
# -----------------------------


class SQLCompileError(Exception):
    """Raised when SQL compilation fails."""

    pass


# -----------------------------
# Compiler
# -----------------------------


class SQLCompiler:
    """
    Compiles a QueryAST and JoinPlan into a SQLAlchemy Select statement.

    Requires SQLAlchemy Table objects to be provided for each table
    referenced in the schema registry.
    """

    def __init__(
        self,
        sqlalchemy_tables: dict,
        registry: SchemaRegistry | None = None,
    ):
        """
        Initialize the compiler.

        Args:
            sqlalchemy_tables: Dict mapping table names to SQLAlchemy Table objects.
                Example: {"orders": orders_table, "products": products_table}
            registry: Schema registry for field lookups.
                     Uses default registry if not provided.
        """
        self._tables = sqlalchemy_tables
        self._registry = registry or get_default_registry()

    def compile(self, ast: QueryAST, join_plan: JoinPlan) -> Select:
        """
        Compile AST + JoinPlan into a SQLAlchemy Select.

        Args:
            ast: The validated QueryAST to compile.
            join_plan: The resolved JoinPlan for the query.

        Returns:
            A SQLAlchemy Select object ready for execution.

        Raises:
            SQLCompileError: If compilation fails.
        """
        base_table = self._tables[join_plan.base_table]

        # 1. Build FROM clause with joins
        from_clause = base_table
        for join in join_plan.joins:
            from_clause = self._apply_join(from_clause, join)

        # 2. Build SELECT columns (dimensions first, then metrics)
        select_columns: list[ColumnElement] = []
        group_by_columns: list[ColumnElement] = []

        for dim in ast.dimensions:
            col = self._resolve_dimension_column(dim.field)
            if dim.alias:
                col = col.label(dim.alias)
            select_columns.append(col)
            group_by_columns.append(self._resolve_dimension_column(dim.field))

        for metric in ast.metrics:
            expr = self._resolve_metric(metric)
            select_columns.append(expr)

        # 3. Build query
        query = select(*select_columns).select_from(from_clause)

        # 4. WHERE filters
        where_clauses = [self._resolve_filter(f) for f in ast.filters]
        if where_clauses:
            query = query.where(and_(*where_clauses))

        # 5. GROUP BY
        if group_by_columns:
            query = query.group_by(*group_by_columns)

        # 6. ORDER BY
        for order in ast.order_by:
            order_expr = self._resolve_order_by(order, ast)
            query = query.order_by(order_expr)

        # 7. LIMIT
        query = query.limit(ast.limit)

        return query

    # -------------------------
    # Join Handling
    # -------------------------

    def _apply_join(self, from_clause, join: JoinStep):
        """Apply a join step to the FROM clause."""
        left = self._tables[join.left_table]
        right = self._tables[join.right_table]

        # Determine if outer join based on join type
        is_outer = join.join_type in (JoinType.LEFT, JoinType.RIGHT, JoinType.FULL)
        is_full = join.join_type == JoinType.FULL

        return from_clause.join(
            right,
            left.c[join.left_key] == right.c[join.right_key],
            isouter=is_outer,
            full=is_full,
        )

    # -------------------------
    # Column Resolution
    # -------------------------

    def _resolve_column(self, field_name: str) -> ColumnElement:
        """Resolve a field name to a SQLAlchemy column."""
        table_name, column_name = self._field_to_table_column(field_name)
        return self._tables[table_name].c[column_name]

    def _resolve_dimension_column(self, field_name: str) -> ColumnElement:
        """Resolve a dimension column, applying date_trunc when configured."""
        col = self._resolve_column(field_name)
        field_meta = self._registry.get_field(field_name)
        if field_meta and field_meta.date_trunc:
            col = func.date_trunc(field_meta.date_trunc, col)
        return col

    def _field_to_table_column(self, field_name: str) -> tuple[str, str]:
        """Map a field name to (table_name, column_name)."""
        # Check regular fields first
        field_meta = self._registry.get_field(field_name)
        if field_meta is not None:
            return field_meta.table, field_meta.column

        # Check derived metrics
        derived = self._registry.get_derived_metric(field_name)
        if derived is not None:
            raise SQLCompileError(
                f"Cannot resolve derived metric '{field_name}' as a column. "
                "Use _resolve_metric instead."
            )

        raise SQLCompileError(f"Unknown field '{field_name}'")

    # -------------------------
    # Metric Resolution
    # -------------------------

    def _resolve_metric(self, metric: Metric) -> ColumnElement:
        """Resolve a metric to a SQLAlchemy aggregate expression."""
        # Check if it's a derived metric
        derived = self._registry.get_derived_metric(metric.field)
        if derived is not None:
            return self._resolve_derived_metric(metric, derived)

        # Regular field metric
        column = self._resolve_column(metric.field)
        agg_expr = self._apply_aggregate(metric.function, column)

        return agg_expr.label(metric.alias or metric.field)

    def _resolve_derived_metric(
        self, metric: Metric, derived: DerivedMetric
    ) -> ColumnElement:
        """Resolve a derived metric to a SQLAlchemy expression."""
        table = self._tables[derived.base_table]

        # Parse and build the expression
        expr = self._parse_expression(derived.expression, table)

        agg_expr = self._apply_aggregate(metric.function, expr)

        return agg_expr.label(metric.alias or metric.field)

    def _parse_expression(self, expression: str, table) -> ColumnElement:
        """
        Parse a symbolic expression into a SQLAlchemy expression.

        Supports simple arithmetic expressions like "quantity * unit_price".
        """
        # Simple expression parser for common patterns
        # In production, consider using a proper expression parser

        expr = expression.strip()

        # Handle multiplication: "a * b"
        if " * " in expr:
            parts = expr.split(" * ")
            if len(parts) == 2:
                left_col = table.c[parts[0].strip()]
                right_col = table.c[parts[1].strip()]
                return left_col * right_col

        # Handle division: "a / b"
        if " / " in expr:
            parts = expr.split(" / ")
            if len(parts) == 2:
                left_col = table.c[parts[0].strip()]
                right_col = table.c[parts[1].strip()]
                return left_col / right_col

        # Handle addition: "a + b"
        if " + " in expr:
            parts = expr.split(" + ")
            if len(parts) == 2:
                left_col = table.c[parts[0].strip()]
                right_col = table.c[parts[1].strip()]
                return left_col + right_col

        # Handle subtraction: "a - b"
        if " - " in expr:
            parts = expr.split(" - ")
            if len(parts) == 2:
                left_col = table.c[parts[0].strip()]
                right_col = table.c[parts[1].strip()]
                return left_col - right_col

        # Single column reference
        if expr in table.c:
            return table.c[expr]

        raise SQLCompileError(
            f"Cannot parse derived metric expression: '{expression}'"
        )

    def _apply_aggregate(
        self, agg_func: AggregateFunction, column: ColumnElement
    ) -> ColumnElement:
        """Apply an aggregate function to a column."""
        match agg_func:
            case AggregateFunction.SUM:
                return func.sum(column)
            case AggregateFunction.COUNT:
                return func.count(column)
            case AggregateFunction.COUNT_DISTINCT:
                return func.count(func.distinct(column))
            case AggregateFunction.AVG:
                return func.avg(column)
            case AggregateFunction.MIN:
                return func.min(column)
            case AggregateFunction.MAX:
                return func.max(column)
            case _:
                raise SQLCompileError(
                    f"Unsupported aggregate function: {agg_func}"
                )

    # -------------------------
    # Filter Resolution
    # -------------------------

    def _resolve_filter(self, filter_: Filter) -> ColumnElement:
        """Resolve a filter to a SQLAlchemy WHERE clause expression."""
        # Handle derived metrics in filters (use base expression)
        derived = self._registry.get_derived_metric(filter_.field)
        if derived is not None:
            table = self._tables[derived.base_table]
            column = self._parse_expression(derived.expression, table)
        else:
            column = self._resolve_column(filter_.field)

        return self._apply_filter_operator(column, filter_.operator, filter_.value)

    def _apply_filter_operator(
        self, column: ColumnElement, operator: FilterOperator, value
    ) -> ColumnElement:
        """Apply a filter operator to a column."""
        match operator:
            case FilterOperator.EQ:
                return column == value
            case FilterOperator.NOT_EQ:
                return column != value
            case FilterOperator.GT:
                return column > value
            case FilterOperator.GTE:
                return column >= value
            case FilterOperator.LT:
                return column < value
            case FilterOperator.LTE:
                return column <= value
            case FilterOperator.BETWEEN:
                return column.between(value[0], value[1])
            case FilterOperator.IN:
                return column.in_(value)
            case FilterOperator.NOT_IN:
                return column.notin_(value)
            case FilterOperator.LIKE:
                return column.like(value)
            case FilterOperator.IS_NULL:
                return column.is_(None)
            case FilterOperator.IS_NOT_NULL:
                return column.isnot(None)
            case _:
                raise SQLCompileError(
                    f"Unsupported filter operator: {operator}"
                )

    # -------------------------
    # Order By Resolution
    # -------------------------

    def _resolve_order_by(self, order: OrderBy, ast: QueryAST) -> ColumnElement:
        """Resolve an ORDER BY clause."""
        # Check if ordering by alias
        for metric in ast.metrics:
            if metric.alias == order.field or metric.field == order.field:
                # For metrics, we need to use the alias in ORDER BY
                col = literal_column(metric.alias or metric.field)
                return col.desc() if order.direction.value == "desc" else col.asc()

        for dim in ast.dimensions:
            if dim.alias == order.field or dim.field == order.field:
                col = self._resolve_dimension_column(dim.field)
                return col.desc() if order.direction.value == "desc" else col.asc()

        raise SQLCompileError(
            f"ORDER BY field '{order.field}' not found in query"
        )
