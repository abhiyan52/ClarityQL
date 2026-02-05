"""Auth API routes."""

from fastapi import APIRouter

from app.api.auth.models import LoginRequest, LoginResponse

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    """Authenticate user (placeholder)."""

    return LoginResponse(access_token="pending")
