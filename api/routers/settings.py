"""Settings API endpoints."""

from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

from fastapi import APIRouter, HTTPException

from dashboard import db
from api.models import (
    SettingsResponse,
    SettingsUpdateRequest,
    TestEmailRequest,
    SuccessResponse,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_settings_from_db() -> SettingsResponse:
    """Load settings from database with env fallbacks."""
    settings = db.get_all_settings()
    
    return SettingsResponse(
        groq_api_key=settings.get("groq_api_key", os.getenv("GROQ_API_KEY", "")),
        llm_provider=settings.get("llm_provider", "groq/llama-3.1-8b-instant"),
        smtp_host=settings.get("smtp_host", os.getenv("SMTP_HOST", "smtp.zoho.in")),
        smtp_port=settings.get("smtp_port", os.getenv("SMTP_PORT", "587")),
        smtp_user=settings.get("smtp_user", os.getenv("SMTP_USER", "")),
        smtp_password=settings.get("smtp_password", os.getenv("SMTP_PASSWORD", "")),
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
    # Update only provided fields
    if request.groq_api_key is not None:
        db.set_setting("groq_api_key", request.groq_api_key)
    if request.llm_provider is not None:
        db.set_setting("llm_provider", request.llm_provider)
    if request.smtp_host is not None:
        db.set_setting("smtp_host", request.smtp_host)
    if request.smtp_port is not None:
        db.set_setting("smtp_port", request.smtp_port)
    if request.smtp_user is not None:
        db.set_setting("smtp_user", request.smtp_user)
    if request.smtp_password is not None:
        db.set_setting("smtp_password", request.smtp_password)
    if request.default_max_scrolls is not None:
        db.set_setting("default_max_scrolls", str(request.default_max_scrolls))
    if request.default_max_inner_pages is not None:
        db.set_setting("default_max_inner_pages", str(request.default_max_inner_pages))
    if request.default_content_limit is not None:
        db.set_setting("default_content_limit", str(request.default_content_limit))
    
    return _get_settings_from_db()


@router.post("/test-email", response_model=SuccessResponse)
async def send_test_email(request: TestEmailRequest) -> SuccessResponse:
    """Send a test email using configured SMTP settings."""
    settings = _get_settings_from_db()
    
    if not request.to_email:
        raise HTTPException(status_code=400, detail="Recipient email is required")
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        raise HTTPException(status_code=400, detail="SMTP settings are incomplete")
    
    try:
        msg = MIMEText(
            "<h2>Crawl4AI Test Email</h2>"
            "<p>If you see this, your SMTP settings are working correctly!</p>",
            "html",
        )
        msg["Subject"] = "Crawl4AI: Test Email"
        msg["From"] = settings.smtp_user
        msg["To"] = request.to_email
        
        with smtplib.SMTP(settings.smtp_host, int(settings.smtp_port)) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_user, [request.to_email], msg.as_string())
        
        return SuccessResponse(message=f"Test email sent to {request.to_email}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")
