"""Schedules API endpoints."""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from dashboard import db
from dashboard.engine import run_job_async
from dashboard.scheduler import get_scheduler, refresh_schedules
from crawl4ai.output.job import generate_job_id
from api.auth import require_any_auth
from api.models import (
    ScheduleCreateRequest,
    ScheduleResponse,
    ScheduleListResponse,
    ScheduleToggleRequest,
    SuccessResponse,
)

router = APIRouter(prefix="/schedules", tags=["schedules"])

_ADMIN_ROLES = {"super_admin", "admin"}


def _parse_config(config: Any) -> Dict[str, Any]:
    """Parse config from string or dict."""
    if isinstance(config, str):
        return json.loads(config)
    return config or {}


def _schedule_to_response(sched: Dict[str, Any]) -> ScheduleResponse:
    """Convert DB schedule dict to response model."""
    return ScheduleResponse(
        id=sched["id"],
        job_name=sched["job_name"],
        url=sched["url"],
        cron=sched["cron"],
        recipients=sched.get("recipients", ""),
        enabled=bool(sched.get("enabled", 1)),
        last_run=str(sched["last_run"]) if sched.get("last_run") else None,
        next_run=str(sched["next_run"]) if sched.get("next_run") else None,
        created_at=str(sched["created_at"]) if sched.get("created_at") else None,
        config=_parse_config(sched.get("config")),
        user_id=sched.get("user_id"),
        consolidated_frequency=sched.get("consolidated_frequency"),
        consolidated_last_sent=str(sched["consolidated_last_sent"]) if sched.get("consolidated_last_sent") else None,
    )


def _check_schedule_ownership(sched: Dict[str, Any], current_user: dict) -> None:
    """Raise 403 if user tries to access a schedule they don't own. Only super_admin bypasses this."""
    if current_user.get("role") == "super_admin":
        return
    if sched.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Access denied: you do not own this schedule")


@router.get("", response_model=ScheduleListResponse)
async def list_schedules(current_user: dict = Depends(require_any_auth)) -> ScheduleListResponse:
    """List schedules. Super admins see all; admins and regular users see only their own."""
    user_id_filter = None if current_user.get("role") == "super_admin" else current_user.get("user_id")
    schedules = db.list_schedules(user_id=user_id_filter)
    return ScheduleListResponse(
        schedules=[_schedule_to_response(s) for s in schedules],
        total=len(schedules),
    )


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: int, current_user: dict = Depends(require_any_auth)
) -> ScheduleResponse:
    """Get details of a specific schedule."""
    sched = db.get_schedule_by_id(schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")
    _check_schedule_ownership(sched, current_user)
    return _schedule_to_response(sched)


@router.post("", response_model=ScheduleResponse)
async def create_schedule(
    request: ScheduleCreateRequest,
    current_user: dict = Depends(require_any_auth),
) -> ScheduleResponse:
    """Create a new recurring schedule."""
    freq = request.consolidated_frequency
    if freq not in ("weekly", "monthly"):
        freq = None

    schedule_id = db.create_schedule(
        job_name=request.job_name,
        url=request.url,
        config=request.config,
        cron=request.cron,
        recipients=request.recipients,
        user_id=current_user.get("user_id"),
        consolidated_frequency=freq,
    )

    if not request.enabled:
        db.update_schedule(schedule_id, enabled=0)

    # Refresh scheduler in background thread to avoid blocking API response
    def _refresh():
        try:
            refresh_schedules()
        except Exception as e:
            print(f"[scheduler] Background refresh failed: {e}")

    threading.Thread(target=_refresh, daemon=True).start()

    sched = db.get_schedule_by_id(schedule_id)
    if not sched:
        raise HTTPException(status_code=500, detail="Failed to create schedule")
    return _schedule_to_response(sched)


@router.put("/{schedule_id}/toggle", response_model=ScheduleResponse)
async def toggle_schedule(
    schedule_id: int,
    request: ScheduleToggleRequest,
    current_user: dict = Depends(require_any_auth),
) -> ScheduleResponse:
    """Enable or disable a schedule."""
    sched = db.get_schedule_by_id(schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")
    _check_schedule_ownership(sched, current_user)

    db.update_schedule(schedule_id, enabled=1 if request.enabled else 0)

    def _refresh():
        try:
            refresh_schedules()
        except Exception as e:
            print(f"[scheduler] Background refresh failed: {e}")

    threading.Thread(target=_refresh, daemon=True).start()

    updated = db.get_schedule_by_id(schedule_id)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update schedule")
    return _schedule_to_response(updated)


@router.post("/{schedule_id}/run-now", response_model=SuccessResponse)
async def run_schedule_now(
    schedule_id: int, current_user: dict = Depends(require_any_auth)
) -> SuccessResponse:
    """Trigger an immediate run of a scheduled job."""
    sched = db.get_schedule_by_id(schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")
    _check_schedule_ownership(sched, current_user)

    config = _parse_config(sched.get("config"))
    job_id = generate_job_id()

    db.create_job(
        job_id=job_id,
        name=f"{sched['job_name']} (manual)",
        url=sched["url"],
        config=config,
        user_id=current_user.get("user_id"),
    )

    run_job_async(job_id)

    return SuccessResponse(
        message=f"Running now as job {job_id}",
        data={"job_id": job_id},
    )


@router.delete("/{schedule_id}", response_model=SuccessResponse)
async def delete_schedule(
    schedule_id: int, current_user: dict = Depends(require_any_auth)
) -> SuccessResponse:
    """Delete a schedule."""
    sched = db.get_schedule_by_id(schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")
    _check_schedule_ownership(sched, current_user)

    db.delete_schedule(schedule_id)

    def _refresh():
        try:
            refresh_schedules()
        except Exception as e:
            print(f"[scheduler] Background refresh failed: {e}")

    threading.Thread(target=_refresh, daemon=True).start()

    return SuccessResponse(message=f"Schedule {schedule_id} deleted successfully")


@router.post("/{schedule_id}/consolidated/send-now", response_model=SuccessResponse)
async def send_consolidated_report_now(
    schedule_id: int, current_user: dict = Depends(require_any_auth)
) -> SuccessResponse:
    """Trigger an on-demand consolidated report for a schedule, regardless of cadence."""
    sched = db.get_schedule_by_id(schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")
    _check_schedule_ownership(sched, current_user)

    if not sched.get("consolidated_frequency"):
        raise HTTPException(
            status_code=400,
            detail="This schedule does not have consolidated reporting enabled",
        )

    def _dispatch():
        import asyncio
        from dashboard.consolidated import generate_and_send_consolidated_report
        settings = db.get_all_settings()
        try:
            asyncio.run(generate_and_send_consolidated_report(sched, settings))
        except Exception as e:
            print(f"[schedules] On-demand consolidated report for {schedule_id} failed: {e}")

    threading.Thread(target=_dispatch, daemon=True).start()

    return SuccessResponse(
        message=f"Consolidated report generation started for schedule {schedule_id}",
        data={"schedule_id": schedule_id},
    )
