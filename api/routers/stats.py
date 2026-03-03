"""Stats API endpoint for dashboard overview."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from dashboard import db
from api.auth import require_any_auth
from api.models import StatsResponse

router = APIRouter(prefix="/stats", tags=["stats"])

_ADMIN_ROLES = {"super_admin", "admin"}


@router.get("", response_model=StatsResponse)
async def get_stats(current_user: dict = Depends(require_any_auth)) -> StatsResponse:
    """Get dashboard statistics scoped to the current user (admins see all)."""
    user_id_filter = None if current_user.get("role") in _ADMIN_ROLES else current_user.get("user_id")

    jobs = db.list_jobs(limit=1000, user_id=user_id_filter)
    schedules = db.list_schedules(user_id=user_id_filter)

    total_jobs = len(jobs)
    running_jobs = sum(1 for j in jobs if j["status"] == "running")
    completed_jobs = sum(1 for j in jobs if j["status"] == "completed")
    failed_jobs = sum(1 for j in jobs if j["status"] == "failed")
    total_articles = sum(j.get("article_count", 0) or 0 for j in jobs)
    active_schedules = sum(1 for s in schedules if s.get("enabled"))

    return StatsResponse(
        total_jobs=total_jobs,
        running_jobs=running_jobs,
        completed_jobs=completed_jobs,
        failed_jobs=failed_jobs,
        total_articles=total_articles,
        active_schedules=active_schedules,
    )
