"""Authentication endpoints (login, current user)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from dashboard import db
from api.auth import verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: int
    username: str
    email: str | None = None
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Authenticate with username/password and receive a JWT token."""
    user = db.get_user_by_username(request.username)

    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact your administrator.",
        )

    token = create_access_token(
        {
            "sub": user["username"],
            "role": user["role"],
            "user_id": user["id"],
        }
    )

    return LoginResponse(
        access_token=token,
        user=UserInfo(
            id=user["id"],
            username=user["username"],
            email=user.get("email"),
            role=user["role"],
        ),
    )


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: dict = Depends(get_current_user)) -> UserInfo:
    """Return the currently authenticated user's profile."""
    user = db.get_user_by_id(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserInfo(
        id=user["id"],
        username=user["username"],
        email=user.get("email"),
        role=user["role"],
    )
