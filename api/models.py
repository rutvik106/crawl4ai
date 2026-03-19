"""Pydantic models for API request/response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---- Job Models ----

class JobCreateRequest(BaseModel):
    """Request model for creating a new job."""
    name: str = Field(..., description="Job name")
    url: str = Field(..., description="URL to crawl")
    schema_fields: Optional[Dict[str, Any]] = Field(None, description="Extraction schema")
    extraction_instruction: str = Field("", description="Custom extraction instruction")
    nav_config: Dict[str, Any] = Field(default_factory=dict, description="Navigation config")
    recipients: str = Field("", description="Email recipients (comma-separated)")
    email_subject: str = Field("", description="Email subject")
    run_async: bool = Field(True, description="Run job immediately after creation")
    summarize_with_ai: bool = Field(False, description="Generate an AI summary and include it in the email")


class JobResponse(BaseModel):
    """Response model for a job."""
    id: str
    name: str
    url: str
    status: str
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    article_count: int = 0
    error: Optional[str] = None
    output_dir: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    user_id: Optional[int] = None


class JobListResponse(BaseModel):
    """Response model for listing jobs."""
    jobs: List[JobResponse]
    total: int


class JobResultsResponse(BaseModel):
    """Response model for job results."""
    job_id: str
    files: List[Dict[str, Any]]
    results: Optional[Any] = None
    blob_urls: Optional[Dict[str, str]] = None


# ---- Schedule Models ----

class ScheduleCreateRequest(BaseModel):
    """Request model for creating a schedule."""
    job_name: str = Field(..., description="Schedule/job name")
    url: str = Field(..., description="URL to crawl")
    config: Dict[str, Any] = Field(default_factory=dict, description="Job configuration")
    cron: str = Field(..., description="Cron expression")
    recipients: str = Field("", description="Email recipients")
    enabled: bool = Field(True, description="Whether schedule is enabled")
    consolidated_frequency: Optional[str] = Field(None, description="Consolidated report cadence: 'weekly', 'monthly', or null")


class ScheduleResponse(BaseModel):
    """Response model for a schedule."""
    id: int
    job_name: str
    url: str
    cron: str
    recipients: str
    enabled: bool
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    created_at: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    user_id: Optional[int] = None
    consolidated_frequency: Optional[str] = None
    consolidated_last_sent: Optional[str] = None


class ScheduleListResponse(BaseModel):
    """Response model for listing schedules."""
    schedules: List[ScheduleResponse]
    total: int


class ScheduleToggleRequest(BaseModel):
    """Request model for toggling schedule enabled state."""
    enabled: bool


# ---- Settings Models ----

class SettingsResponse(BaseModel):
    """Response model for settings."""
    groq_api_key: str = ""
    llm_provider: str = "groq/llama-3.1-8b-instant"
    default_max_scrolls: int = 10
    default_max_inner_pages: int = 5
    default_content_limit: int = 12000


class SettingsUpdateRequest(BaseModel):
    """Request model for updating settings."""
    groq_api_key: Optional[str] = None
    llm_provider: Optional[str] = None
    default_max_scrolls: Optional[int] = None
    default_max_inner_pages: Optional[int] = None
    default_content_limit: Optional[int] = None


class TestEmailRequest(BaseModel):
    """Request model for sending test email."""
    to_email: str


# ---- Stats Models ----

class StatsResponse(BaseModel):
    """Response model for dashboard stats."""
    total_jobs: int
    running_jobs: int
    completed_jobs: int
    failed_jobs: int
    total_articles: int
    active_schedules: int


# ---- Generic Response Models ----

class SuccessResponse(BaseModel):
    """Generic success response."""
    success: bool = True
    message: str = ""
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """Generic error response."""
    success: bool = False
    error: str
    detail: Optional[str] = None
