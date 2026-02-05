"""Pydantic models for NLQ requests and responses."""

from pydantic import BaseModel


class NLQQueryRequest(BaseModel):
    """Incoming NLQ query payload."""

    query: str


class NLQQueryResponse(BaseModel):
    """Placeholder NLQ response payload."""

    request_id: str
    status: str
