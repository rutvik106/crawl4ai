"""Authentication utilities for JWT-based auth."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "crawl4ai-secret-key-change-in-production-2024")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24 hours

security = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt. Truncates to 72 bytes (bcrypt limit)."""
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    password_bytes = plain_password.encode("utf-8")[:72]
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def create_access_token(data: dict) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Decode the JWT and verify the account is still active and not expired."""
    payload = decode_token(credentials.credentials)

    # Avoid circular import — import here so auth.py stays a utility module
    from dashboard import db

    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user_id",
        )

    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists",
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact your administrator.",
        )

    expires_at = user.get("expires_at")
    if expires_at is not None:
        now = datetime.now(timezone.utc)
        # expires_at may be timezone-aware or naive depending on DB driver
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account access has expired. Contact your administrator.",
            )

    return payload


def require_role(*roles: str):
    """Return a FastAPI dependency that enforces one of the given roles."""
    def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(roles)}",
            )
        return current_user
    return role_checker


# Convenience dependencies
require_any_auth = get_current_user
require_admin = require_role("admin", "super_admin")
require_super_admin = require_role("super_admin")
