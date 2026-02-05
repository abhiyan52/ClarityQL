"""Schema API routes."""

from fastapi import APIRouter

from packages.core.schema_registry.registry import get_default_registry

router = APIRouter()


@router.get("")
async def get_schema() -> dict:
    """
    Get the available schema for queries.

    Returns tables, fields, and derived metrics that can be queried.
    """
    registry = get_default_registry()

    tables = []
    for table_name in registry.list_tables():
        table = registry.get_table(table_name)
        if table:
            fields = []
            for field_name, field_meta in table.fields.items():
                field_info = {
                    "name": field_name,
                    "type": field_meta.field_type.value,
                    "description": field_meta.description,
                    "aggregatable": field_meta.aggregatable,
                }
                if field_meta.allowed_values:
                    field_info["allowed_values"] = list(field_meta.allowed_values)
                fields.append(field_info)

            tables.append({
                "name": table_name,
                "description": table.description,
                "fields": fields,
            })

    derived_metrics = []
    for metric_name in registry.list_derived_metrics():
        metric = registry.get_derived_metric(metric_name)
        if metric:
            derived_metrics.append({
                "name": metric_name,
                "description": metric.description,
                "expression": metric.expression,
            })

    return {
        "tables": tables,
        "derived_metrics": derived_metrics,
    }
