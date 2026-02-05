"""Pydantic models for schema discovery."""

from pydantic import BaseModel


class SchemaListResponse(BaseModel):
    """Placeholder response for available schemas."""

    schemas: list[str]
