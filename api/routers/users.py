"""User management endpoints (admin + super_admin only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from dashboard import db
from api.auth import hash_password, require_admin, require_super_admin, get_current_user

router = APIRouter(prefix="/users", tags=["users"])


# ---- Models ----

class CreateUserRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "user"  # "user" or "admin"
    expires_at: Optional[datetime] = None  # ISO-8601 datetime; None = no expiry


class UpdateExpiryRequest(BaseModel):
    expires_at: Optional[datetime] = None  # None clears the expiry


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[str] = None
    created_by_username: Optional[str] = None
    expires_at: Optional[str] = None
    is_expired: bool = False


# ---- Helpers ----

def _is_expired(user: dict) -> bool:
    expires_at = user.get("expires_at")
    if expires_at is None:
        return False
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return now > expires_at


def _to_response(user: dict) -> UserResponse:
    creator_name: Optional[str] = None
    if user.get("created_by"):
        creator = db.get_user_by_id(user["created_by"])
        creator_name = creator["username"] if creator else None
    expires_at = user.get("expires_at")
    return UserResponse(
        id=user["id"],
        username=user["username"],
        email=user.get("email"),
        role=user["role"],
        is_active=user["is_active"],
        created_at=str(user["created_at"]) if user.get("created_at") else None,
        created_by_username=creator_name,
        expires_at=str(expires_at) if expires_at else None,
        is_expired=_is_expired(user),
    )


# ---- Endpoints ----

@router.get("", response_model=List[UserResponse])
async def list_users(current_user: dict = Depends(require_admin)) -> List[UserResponse]:
    """
    List users.
    - super_admin: sees all users
    - admin: sees only users they created
    """
    if current_user["role"] == "super_admin":
        users = db.list_users()
    else:
        users = db.list_users(created_by=current_user["user_id"])
    return [_to_response(u) for u in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: CreateUserRequest,
    current_user: dict = Depends(require_admin),
) -> UserResponse:
    """
    Create a new user.
    - super_admin can create users with role 'user' or 'admin', and set an expiry date
    - admin can only create users with role 'user', and set an expiry date
    """
    if request.role not in ("user", "admin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'user' or 'admin'",
        )

    if current_user["role"] == "admin" and request.role != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins can only create users with role 'user'",
        )

    if db.get_user_by_username(request.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    user = db.create_user(
        username=request.username,
        password_hash=hash_password(request.password),
        role=request.role,
        email=request.email,
        created_by=current_user["user_id"],
        expires_at=request.expires_at,
    )
    return _to_response(user)


@router.put("/{user_id}/expiry", response_model=UserResponse)
async def set_user_expiry(
    user_id: int,
    request: UpdateExpiryRequest,
    current_user: dict = Depends(require_admin),
) -> UserResponse:
    """
    Set or clear the expiry date for a user account.
    - Passing expires_at sets the expiry
    - Passing expires_at=null clears the expiry (unlimited access)
    - super_admin accounts cannot have an expiry set
    """
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user["role"] == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot set expiry on the super admin account",
        )

    # Admins may only manage users they created
    if current_user["role"] == "admin" and user.get("created_by") != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage users you created",
        )

    db.update_user(user_id, expires_at=request.expires_at)

    # If the new expiry is in the past (or was cleared), re-enable the account so admins
    # can extend access by just updating the expiry date
    if request.expires_at is not None:
        expires_at = request.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if expires_at > now and not user.get("is_active", True):
            # Expiry extended beyond now — re-activate the account
            db.update_user(user_id, is_active=True)

    updated = db.get_user_by_id(user_id)
    return _to_response(updated)


@router.put("/{user_id}/toggle", response_model=UserResponse)
async def toggle_user(
    user_id: int,
    current_user: dict = Depends(require_admin),
) -> UserResponse:
    """Enable or disable a user account."""
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user["role"] == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot disable the super admin account",
        )

    # Admins may only manage users they created
    if current_user["role"] == "admin" and user.get("created_by") != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage users you created",
        )

    db.update_user(user_id, is_active=not user["is_active"])
    updated = db.get_user_by_id(user_id)
    return _to_response(updated)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: dict = Depends(require_admin),
) -> dict:
    """Delete a user account."""
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user["role"] == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete the super admin account",
        )

    if user["id"] == current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete your own account",
        )

    # Admins may only delete users they created
    if current_user["role"] == "admin" and user.get("created_by") != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete users you created",
        )

    db.delete_user(user_id)
    return {"success": True, "message": f"User '{user['username']}' deleted"}
