"""
AST Validator for ClarityQL.

Validates semantic correctness of a QueryAST using the schema registry.
"""

from packages.core.schema_registry.registry import (
    FieldMeta,
    FieldType,
    SchemaRegistry,
    get_default_registry,
)
from packages.core.sql_ast.models import (
    Dimension,
    Filter,
    FilterOperator,
    Metric,
    QueryAST,
)


# -----------------------------
# Errors
# -----------------------------


class ASTValidationError(Exception):
    """Raised when an AST is semantically invalid."""

    pass


# -----------------------------
# Operator Validation Rules
# -----------------------------

# Operators allowed for each field type
ALLOWED_OPERATORS: dict[FieldType, set[FilterOperator]] = {
    FieldType.STRING: {
        FilterOperator.EQ,
        FilterOperator.NOT_EQ,
        FilterOperator.IN,
        FilterOperator.NOT_IN,
        FilterOperator.LIKE,
        FilterOperator.IS_NULL,
        FilterOperator.IS_NOT_NULL,
    },
    FieldType.NUMERIC: {
        FilterOperator.EQ,
        FilterOperator.NOT_EQ,
        FilterOperator.GT,
        FilterOperator.GTE,
        FilterOperator.LT,
        FilterOperator.LTE,
        FilterOperator.BETWEEN,
        FilterOperator.IN,
        FilterOperator.NOT_IN,
        FilterOperator.IS_NULL,
        FilterOperator.IS_NOT_NULL,
    },
    FieldType.DATE: {
        FilterOperator.EQ,
        FilterOperator.NOT_EQ,
        FilterOperator.GT,
        FilterOperator.GTE,
        FilterOperator.LT,
        FilterOperator.LTE,
        FilterOperator.BETWEEN,
        FilterOperator.IS_NULL,
        FilterOperator.IS_NOT_NULL,
    },
    FieldType.TIMESTAMP: {
        FilterOperator.EQ,
        FilterOperator.NOT_EQ,
        FilterOperator.GT,
        FilterOperator.GTE,
        FilterOperator.LT,
        FilterOperator.LTE,
        FilterOperator.BETWEEN,
        FilterOperator.IS_NULL,
        FilterOperator.IS_NOT_NULL,
    },
    FieldType.BOOLEAN: {
        FilterOperator.EQ,
        FilterOperator.NOT_EQ,
        FilterOperator.IS_NULL,
        FilterOperator.IS_NOT_NULL,
    },
}


# -----------------------------
# Validator
# -----------------------------


class ASTValidator:
    """
    Validates QueryAST objects against the schema registry.

    Ensures all fields exist, are used appropriately, and operators
    are valid for the field types.
    """

    def __init__(self, registry: SchemaRegistry | None = None):
        """
        Initialize the validator.

        Args:
            registry: Schema registry to validate against.
                     Uses default registry if not provided.
        """
        self._registry = registry or get_default_registry()

    def validate(self, ast: QueryAST) -> None:
        """
        Validate the given AST.

        Args:
            ast: The QueryAST to validate.

        Raises:
            ASTValidationError: If the AST is semantically invalid.
        """
        self._validate_metrics(ast.metrics)
        self._validate_dimensions(ast.dimensions)
        self._validate_filters(ast.filters)
        self._validate_order_by(ast)
        self._validate_limit(ast.limit)

    # -------------------------
    # Validation Methods
    # -------------------------

    def _validate_metrics(self, metrics: list[Metric]) -> None:
        """Validate all metrics in the query."""
        for metric in metrics:
            # Check if field exists
            if not self._registry.field_exists(metric.field):
                raise ASTValidationError(
                    f"Unknown metric field '{metric.field}'"
                )

            # Derived metrics are always valid for aggregation
            if self._registry.get_derived_metric(metric.field) is not None:
                continue

            # Physical field - check if aggregatable
            field_meta = self._registry.get_field(metric.field)
            if field_meta and not field_meta.aggregatable:
                raise ASTValidationError(
                    f"Field '{metric.field}' is not aggregatable"
                )

    def _validate_dimensions(self, dimensions: list[Dimension]) -> None:
        """Validate all dimensions in the query."""
        for dim in dimensions:
            if not self._registry.field_exists(dim.field):
                raise ASTValidationError(
                    f"Unknown dimension field '{dim.field}'"
                )

    def _validate_filters(self, filters: list[Filter]) -> None:
        """Validate all filters in the query."""
        for f in filters:
            # Check field exists
            if not self._registry.field_exists(f.field):
                raise ASTValidationError(
                    f"Unknown filter field '{f.field}'"
                )

            # Get field metadata (skip operator validation for derived metrics)
            field_meta = self._registry.get_field(f.field)
            if field_meta is None:
                # Derived metric - allow all operators
                continue

            # Validate operator is allowed for this field type
            self._validate_operator(f, field_meta)

            # Validate value matches operator expectations
            self._validate_filter_value(f, field_meta)

    def _validate_operator(self, f: Filter, field_meta: FieldMeta) -> None:
        """Validate that the operator is allowed for the field type."""
        allowed = ALLOWED_OPERATORS.get(field_meta.field_type, set())

        if f.operator not in allowed:
            raise ASTValidationError(
                f"Operator '{f.operator.value}' not allowed for "
                f"{field_meta.field_type.value} field '{f.field}'"
            )

    def _validate_filter_value(self, f: Filter, field_meta: FieldMeta) -> None:
        """Validate that the filter value matches operator expectations."""
        # BETWEEN requires a 2-element sequence
        if f.operator == FilterOperator.BETWEEN:
            if not isinstance(f.value, (list, tuple)) or len(f.value) != 2:
                raise ASTValidationError(
                    f"BETWEEN operator for '{f.field}' requires exactly 2 values"
                )

        # IN/NOT_IN requires a list
        if f.operator in (FilterOperator.IN, FilterOperator.NOT_IN):
            if not isinstance(f.value, (list, tuple)):
                raise ASTValidationError(
                    f"IN/NOT_IN operator for '{f.field}' requires a list of values"
                )

        # IS_NULL/IS_NOT_NULL should not have a value (or value should be None/ignored)
        # We allow any value here since the operator itself is sufficient

    def _validate_order_by(self, ast: QueryAST) -> None:
        """Validate ORDER BY fields are in SELECT list."""
        valid_fields = {m.field for m in ast.metrics} | {d.field for d in ast.dimensions}

        # Also include aliases if present
        for m in ast.metrics:
            if m.alias:
                valid_fields.add(m.alias)
        for d in ast.dimensions:
            if d.alias:
                valid_fields.add(d.alias)

        for order in ast.order_by:
            if order.field not in valid_fields:
                raise ASTValidationError(
                    f"ORDER BY field '{order.field}' must be a metric or dimension"
                )

    def _validate_limit(self, limit: int) -> None:
        """Validate limit is within bounds."""
        if limit > 1000:
            raise ASTValidationError(
                f"Limit {limit} exceeds maximum allowed value of 1000"
            )
        if limit < 1:
            raise ASTValidationError(
                f"Limit {limit} must be at least 1"
            )
