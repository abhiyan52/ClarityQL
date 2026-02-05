"""NLQ API routes."""

from fastapi import APIRouter

from app.api.nlq.models import NLQQueryRequest, NLQQueryResponse

router = APIRouter()


@router.post("/query", response_model=NLQQueryResponse)
def submit_nlq_query(payload: NLQQueryRequest) -> NLQQueryResponse:
    """Accept a natural language query (placeholder)."""

    return NLQQueryResponse(request_id="pending", status="queued")
