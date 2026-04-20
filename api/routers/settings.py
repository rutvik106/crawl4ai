"""Settings API endpoints."""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

from fastapi import APIRouter, Depends, HTTPException

from dashboard import db
from api.auth import require_super_admin
from api.models import (
    SettingsResponse,
    SettingsUpdateRequest,
    TestEmailRequest,
    SuccessResponse,
)

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_super_admin)])

EMAIL_API_URL = "https://time-tracker-3-sigma.vercel.app/api/v1/users/emailsend"


def _get_settings_from_db() -> SettingsResponse:
    """Load settings from database with env fallbacks."""
    settings = db.get_all_settings()

    return SettingsResponse(
        groq_api_key=settings.get("groq_api_key", os.getenv("GROQ_API_KEY", "")),
        llm_provider=settings.get("llm_provider", "groq/llama-3.1-8b-instant"),
        default_max_scrolls=int(settings.get("default_max_scrolls", "10")),
        default_max_inner_pages=int(settings.get("default_max_inner_pages", "5")),
        default_content_limit=int(settings.get("default_content_limit", "12000")),
    )


@router.get("", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    """Get all settings."""
    return _get_settings_from_db()


@router.put("", response_model=SettingsResponse)
async def update_settings(request: SettingsUpdateRequest) -> SettingsResponse:
    """Update settings."""
    if request.groq_api_key is not None:
        db.set_setting("groq_api_key", request.groq_api_key)
    if request.llm_provider is not None:
        db.set_setting("llm_provider", request.llm_provider)
    if request.default_max_scrolls is not None:
        db.set_setting("default_max_scrolls", str(request.default_max_scrolls))
    if request.default_max_inner_pages is not None:
        db.set_setting("default_max_inner_pages", str(request.default_max_inner_pages))
    if request.default_content_limit is not None:
        db.set_setting("default_content_limit", str(request.default_content_limit))

    return _get_settings_from_db()


@router.post("/test-email", response_model=SuccessResponse)
async def send_test_email(request: TestEmailRequest) -> SuccessResponse:
    """Send a test email using the email API."""
    if not request.to_email:
        raise HTTPException(status_code=400, detail="Recipient email is required")

    payload = {
        "to": request.to_email,
        "subject": "Test Email",
        "html": "<h2>Test Email</h2><p>If you see this, your email delivery is working correctly!</p>",
        "text": "Test Email - If you see this, your email delivery is working correctly!",
    }

    req = urllib.request.Request(
        EMAIL_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status not in (200, 201, 202):
                raise HTTPException(status_code=500, detail=f"Email API returned {response.status}")
        return SuccessResponse(message=f"Test email sent to {request.to_email}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        raise HTTPException(status_code=500, detail=f"Failed to send email: HTTP {e.code}: {body}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")
