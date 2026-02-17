"""Schedules API endpoints."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from dashboard import db
from dashboard.engine import run_job_async
from dashboard.scheduler import get_scheduler, refresh_schedules
from crawl4ai.output.job import generate_job_id
from api.models import (
    ScheduleCreateRequest,
    ScheduleResponse,
    ScheduleListResponse,
    ScheduleToggleRequest,
    SuccessResponse,
)

router = APIRouter(prefix="/schedules", tags=["schedules"])


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
    )


@router.get("", response_model=ScheduleListResponse)
async def list_schedules() -> ScheduleListResponse:
    """List all scheduled jobs."""
    schedules = db.list_schedules()
    return ScheduleListResponse(
        schedules=[_schedule_to_response(s) for s in schedules],
        total=len(schedules),
    )


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(schedule_id: int) -> ScheduleResponse:
    """Get details of a specific schedule."""
    schedules = db.list_schedules()
    for sched in schedules:
        if sched["id"] == schedule_id:
            return _schedule_to_response(sched)
    raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")


@router.post("", response_model=ScheduleResponse)
async def create_schedule(request: ScheduleCreateRequest) -> ScheduleResponse:
    """Create a new recurring schedule."""
    schedule_id = db.create_schedule(
        job_name=request.job_name,
        url=request.url,
        config=request.config,
        cron=request.cron,
        recipients=request.recipients,
    )
    
    if not request.enabled:
        db.update_schedule(schedule_id, enabled=0)
    
    # Refresh scheduler
    refresh_schedules()
    
    # Get the created schedule
    schedules = db.list_schedules()
    for sched in schedules:
        if sched["id"] == schedule_id:
            return _schedule_to_response(sched)
    
    raise HTTPException(status_code=500, detail="Failed to create schedule")


@router.put("/{schedule_id}/toggle", response_model=ScheduleResponse)
async def toggle_schedule(schedule_id: int, request: ScheduleToggleRequest) -> ScheduleResponse:
    """Enable or disable a schedule."""
    # Check if schedule exists
    schedules = db.list_schedules()
    found = None
    for sched in schedules:
        if sched["id"] == schedule_id:
            found = sched
            break
    
    if not found:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")
    
    # Update enabled status
    db.update_schedule(schedule_id, enabled=1 if request.enabled else 0)
    
    # Refresh scheduler
    refresh_schedules()
    
    # Return updated schedule
    schedules = db.list_schedules()
    for sched in schedules:
        if sched["id"] == schedule_id:
            return _schedule_to_response(sched)
    
    raise HTTPException(status_code=500, detail="Failed to update schedule")


@router.post("/{schedule_id}/run-now", response_model=SuccessResponse)
async def run_schedule_now(schedule_id: int) -> SuccessResponse:
    """Trigger an immediate run of a scheduled job."""
    # Find the schedule
    schedules = db.list_schedules()
    sched = None
    for s in schedules:
        if s["id"] == schedule_id:
            sched = s
            break
    
    if not sched:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")
    
    config = _parse_config(sched.get("config"))
    job_id = generate_job_id()
    
    db.create_job(
        job_id=job_id,
        name=f"{sched['job_name']} (manual)",
        url=sched["url"],
        config=config,
    )
    
    run_job_async(job_id)
    
    return SuccessResponse(
        message=f"Running now as job {job_id}",
        data={"job_id": job_id},
    )


@router.delete("/{schedule_id}", response_model=SuccessResponse)
async def delete_schedule(schedule_id: int) -> SuccessResponse:
    """Delete a schedule."""
    # Check if schedule exists
    schedules = db.list_schedules()
    found = False
    for sched in schedules:
        if sched["id"] == schedule_id:
            found = True
            break
    
    if not found:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")
    
    db.delete_schedule(schedule_id)
    refresh_schedules()
    
    return SuccessResponse(message=f"Schedule {schedule_id} deleted successfully")
