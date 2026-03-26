"""GET /api/logs — stream recent in-memory server logs to Claude or admins."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from api.auth import get_current_user
from dashboard.log_buffer import get_recent_logs, buffer_size

router = APIRouter(tags=["logs"])


@router.get("/logs")
async def read_logs(
    limit: int = Query(200, ge=1, le=2000, description="Max lines to return"),
    level: str = Query("INFO", description="Min level: DEBUG / INFO / WARNING / ERROR / CRITICAL"),
    logger_filter: Optional[str] = Query(None, description="Filter by logger name substring"),
    current_user: dict = Depends(get_current_user),
):
    """
    Return recent in-memory server logs.

    Requires a valid Bearer token. Useful for Claude or admins to diagnose
    stuck scheduled jobs and other runtime issues without SSH/Railway access.

    Example:
        GET /api/logs?level=WARNING&limit=100
    """
    logs = get_recent_logs(limit=limit, min_level=level, logger_filter=logger_filter)
    return {
        "total": len(logs),
        "buffer_size": buffer_size(),
        "min_level": level.upper(),
        "logger_filter": logger_filter,
        "logs": logs,
    }
