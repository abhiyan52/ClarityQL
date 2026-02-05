"""Authentication schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Request schema for login."""

    email: EmailStr
    password: str = Field(min_length=6)


class LoginResponse(BaseModel):
    """Response schema for successful login."""

    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    """Request schema for user registration."""

    email: EmailStr
    password: str = Field(min_length=6)


class UserResponse(BaseModel):
    """Response schema for user info."""

    id: UUID
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}
