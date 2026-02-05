"""Auth API routes."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import AsyncSessionDep, CurrentUser
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UserResponse,
)

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSessionDep,
) -> LoginResponse:
    """
    Authenticate user and return JWT token.

    Args:
        payload: Login credentials (email, password).
        session: Database session.

    Returns:
        JWT access token.

    Raises:
        HTTPException 401: If credentials are invalid.
    """
    # Find user by email
    result = await session.execute(
        select(User).where(User.email == payload.email)
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(subject=str(user.id))

    return LoginResponse(access_token=access_token)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: AsyncSessionDep,
) -> User:
    """
    Register a new user.

    Args:
        payload: Registration data (email, password).
        session: Database session.

    Returns:
        Created user info.

    Raises:
        HTTPException 400: If email already exists.
    """
    # Check if email already exists
    result = await session.execute(
        select(User).where(User.email == payload.email)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)

    return user


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: CurrentUser,
) -> User:
    """
    Get current authenticated user info.

    Args:
        current_user: The authenticated user (from JWT).

    Returns:
        User info.
    """
    return current_user
