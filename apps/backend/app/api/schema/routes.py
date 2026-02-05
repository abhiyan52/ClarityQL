"""Schema API routes."""

from fastapi import APIRouter

from app.api.schema.models import SchemaListResponse

router = APIRouter()


@router.get("/list", response_model=SchemaListResponse)
def list_schemas() -> SchemaListResponse:
    """Return available schemas (placeholder)."""

    return SchemaListResponse(schemas=[])
