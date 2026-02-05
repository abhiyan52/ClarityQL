"""
AST Merge Logic for ClarityQL.

Merges a delta AST (from a follow-up query) with a previous AST
to produce a refined query while preserving context.

Merge Rules:
- Metrics: Replace if delta has metrics, else keep previous
- Dimensions: Extend and dedupe if delta has dimensions, else keep previous
- Filters: Merge by field (new filter on same field overrides old)
- Order By: Keep previous unless delta explicitly provides new ordering
- Limit: Use delta if provided, else keep previous
"""

from packages.core.sql_ast.models import (
    QueryAST,
    Metric,
    Dimension,
    Filter,
    OrderBy,
)


class ASTMergeError(Exception):
    """Raised when AST merge fails."""

    pass


def merge_ast(previous: QueryAST, delta: QueryAST) -> QueryAST:
    """
    Merge a delta AST into a previous AST.

    The delta represents changes from a follow-up query.
    The result is a new AST that refines the previous query.

    Args:
        previous: The AST from the previous query.
        delta: The AST from the follow-up query (may be partial).

    Returns:
        A new merged QueryAST.

    Raises:
        ASTMergeError: If merge produces an invalid AST.
    """
    try:
        return QueryAST(
            metrics=_merge_metrics(previous.metrics, delta.metrics),
            dimensions=_merge_dimensions(previous.dimensions, delta.dimensions),
            filters=_merge_filters(previous.filters, delta.filters),
            order_by=_merge_order_by(previous.order_by, delta.order_by),
            limit=_merge_limit(previous.limit, delta.limit),
        )
    except Exception as e:
        raise ASTMergeError(f"Failed to merge AST: {e}") from e


def _merge_metrics(
    previous: list[Metric],
    delta: list[Metric],
) -> list[Metric]:
    """
    Merge metrics from previous and delta AST.

    Rule: If delta has metrics, replace previous. Otherwise keep previous.
    This ensures the user can switch to a different metric if needed.
    """
    # Check if delta has "real" metrics (not just a placeholder from the LLM)
    if delta and len(delta) > 0:
        # If delta metrics look substantive, use them
        # But if they're identical to previous, keep previous
        delta_set = {(m.function, m.field) for m in delta}
        prev_set = {(m.function, m.field) for m in previous}

        if delta_set != prev_set:
            # Delta has different metrics - this might be intentional
            # or might be the LLM filling in defaults
            # For REFINE queries, we typically keep previous metrics
            # unless delta explicitly changes them
            return delta

    return previous


def _merge_dimensions(
    previous: list[Dimension],
    delta: list[Dimension],
) -> list[Dimension]:
    """
    Merge dimensions from previous and delta AST.

    Rule: Extend and deduplicate. Delta dimensions are added to previous.
    """
    if not delta:
        return previous

    # Create a set of existing dimension fields for deduplication
    existing_fields = {d.field for d in previous}

    # Start with previous dimensions
    merged = list(previous)

    # Add new dimensions from delta
    for dim in delta:
        if dim.field not in existing_fields:
            merged.append(dim)
            existing_fields.add(dim.field)

    return merged


def _merge_filters(
    previous: list[Filter],
    delta: list[Filter],
) -> list[Filter]:
    """
    Merge filters from previous and delta AST.

    Rule: Merge by field. New filter on same field overrides old one.
    This allows users to refine filters (e.g., "for Europe" after "by region").
    """
    if not delta:
        return previous

    # Create a dict of previous filters by field
    filter_map: dict[str, Filter] = {f.field: f for f in previous}

    # Override/add with delta filters
    for f in delta:
        filter_map[f.field] = f

    return list(filter_map.values())


def _merge_order_by(
    previous: list[OrderBy],
    delta: list[OrderBy],
) -> list[OrderBy]:
    """
    Merge order_by from previous and delta AST.

    Rule: Keep previous unless delta explicitly provides new ordering.
    """
    if delta:
        return delta

    return previous


def _merge_limit(previous: int, delta: int) -> int:
    """
    Merge limit from previous and delta AST.

    Rule: Use delta if it's different from the default (50),
    otherwise keep previous.
    """
    # If delta limit is different from default, use it
    if delta != 50:
        return delta

    return previous


# -----------------------------
# Utility functions
# -----------------------------


def is_delta_empty(delta: QueryAST) -> bool:
    """
    Check if a delta AST is effectively empty (only has default values).

    This helps determine if the LLM produced a meaningful delta
    or just returned defaults.
    """
    # Check if only defaults
    has_custom_metrics = len(delta.metrics) > 0
    has_dimensions = len(delta.dimensions) > 0
    has_filters = len(delta.filters) > 0
    has_order = len(delta.order_by) > 0
    has_custom_limit = delta.limit != 50

    return not (has_dimensions or has_filters or has_order or has_custom_limit)


def ast_diff(previous: QueryAST, current: QueryAST) -> dict:
    """
    Compute the difference between two ASTs.

    Useful for explaining what changed in a follow-up query.
    """
    diff = {}

    # Compare metrics
    prev_metrics = {(m.function, m.field) for m in previous.metrics}
    curr_metrics = {(m.function, m.field) for m in current.metrics}
    if prev_metrics != curr_metrics:
        diff["metrics"] = {
            "added": list(curr_metrics - prev_metrics),
            "removed": list(prev_metrics - curr_metrics),
        }

    # Compare dimensions
    prev_dims = {d.field for d in previous.dimensions}
    curr_dims = {d.field for d in current.dimensions}
    if prev_dims != curr_dims:
        diff["dimensions"] = {
            "added": list(curr_dims - prev_dims),
            "removed": list(prev_dims - curr_dims),
        }

    # Compare filters
    prev_filters = {f.field: (f.operator, f.value) for f in previous.filters}
    curr_filters = {f.field: (f.operator, f.value) for f in current.filters}
    if prev_filters != curr_filters:
        diff["filters"] = {
            "added": [f for f in curr_filters if f not in prev_filters],
            "changed": [
                f for f in curr_filters
                if f in prev_filters and curr_filters[f] != prev_filters[f]
            ],
            "removed": [f for f in prev_filters if f not in curr_filters],
        }

    # Compare order
    prev_order = [(o.field, o.direction) for o in previous.order_by]
    curr_order = [(o.field, o.direction) for o in current.order_by]
    if prev_order != curr_order:
        diff["order_by"] = {"previous": prev_order, "current": curr_order}

    # Compare limit
    if previous.limit != current.limit:
        diff["limit"] = {"previous": previous.limit, "current": current.limit}

    return diff
