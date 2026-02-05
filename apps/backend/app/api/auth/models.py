"""Pydantic models for auth payloads."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Placeholder login request."""

    email: str
    password: str


class LoginResponse(BaseModel):
    """Placeholder login response."""

    access_token: str
    token_type: str = "bearer"
