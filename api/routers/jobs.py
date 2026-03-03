"""Jobs API endpoints."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard import db
from dashboard.engine import run_job_async
from dashboard.scheduler import refresh_schedules
from crawl4ai.output.job import generate_job_id
from api.auth import require_any_auth
from api.models import (
    JobCreateRequest,
    JobResponse,
    JobListResponse,
    JobResultsResponse,
    SuccessResponse,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])

_ADMIN_ROLES = {"super_admin", "admin"}


def _parse_config(config: Any) -> Dict[str, Any]:
    """Parse config from string or dict."""
    if isinstance(config, str):
        return json.loads(config)
    return config or {}


def _job_to_response(job: Dict[str, Any]) -> JobResponse:
    """Convert DB job dict to response model."""
    return JobResponse(
        id=job["id"],
        name=job["name"],
        url=job["url"],
        status=job["status"],
        created_at=str(job["created_at"]) if job.get("created_at") else None,
        started_at=str(job["started_at"]) if job.get("started_at") else None,
        finished_at=str(job["finished_at"]) if job.get("finished_at") else None,
        article_count=job.get("article_count", 0) or 0,
        error=job.get("error"),
        output_dir=job.get("output_dir"),
        config=_parse_config(job.get("config")),
        user_id=job.get("user_id"),
    )


def _check_job_ownership(job: Dict[str, Any], current_user: dict) -> None:
    """Raise 403 if a regular user tries to access a job they don't own."""
    if current_user.get("role") in _ADMIN_ROLES:
        return
    if job.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Access denied: you do not own this job")


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of jobs to return"),
    current_user: dict = Depends(require_any_auth),
) -> JobListResponse:
    """List jobs. Admins see all jobs; regular users see only their own."""
    user_id_filter = None if current_user.get("role") in _ADMIN_ROLES else current_user.get("user_id")
    jobs = db.list_jobs(limit=limit, user_id=user_id_filter)

    if status:
        jobs = [j for j in jobs if j["status"] == status]

    return JobListResponse(
        jobs=[_job_to_response(j) for j in jobs],
        total=len(jobs),
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, current_user: dict = Depends(require_any_auth)) -> JobResponse:
    """Get details of a specific job."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    _check_job_ownership(job, current_user)
    return _job_to_response(job)


@router.post("", response_model=JobResponse)
async def create_job(
    request: JobCreateRequest,
    current_user: dict = Depends(require_any_auth),
) -> JobResponse:
    """Create a new crawl job."""
    job_id = generate_job_id()

    config = {
        **request.nav_config,
        "schema_fields": request.schema_fields or {},
        "extraction_instruction": request.extraction_instruction,
        "recipients": request.recipients,
        "email_subject": request.email_subject,
        "summarize_with_ai": request.summarize_with_ai,
    }

    job = db.create_job(
        job_id=job_id,
        name=request.name,
        url=request.url,
        config=config,
        user_id=current_user.get("user_id"),
    )

    if request.run_async:
        run_job_async(job_id)

    return _job_to_response(job)


@router.post("/{job_id}/rerun", response_model=JobResponse)
async def rerun_job(job_id: str, current_user: dict = Depends(require_any_auth)) -> JobResponse:
    """Re-run an existing job with the same configuration."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    _check_job_ownership(job, current_user)

    config = _parse_config(job.get("config"))
    new_id = generate_job_id()

    new_job = db.create_job(
        job_id=new_id,
        name=job["name"],
        url=job["url"],
        config=config,
        user_id=current_user.get("user_id"),
    )

    run_job_async(new_id)

    return _job_to_response(new_job)


@router.delete("/{job_id}", response_model=SuccessResponse)
async def delete_job(job_id: str, current_user: dict = Depends(require_any_auth)) -> SuccessResponse:
    """Delete a job and its output files."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    _check_job_ownership(job, current_user)

    # Delete from database
    db.delete_job(job_id)

    # Refresh schedules
    refresh_schedules()

    # Clean up output directory
    output_dir = job.get("output_dir")
    if output_dir and os.path.exists(output_dir):
        try:
            shutil.rmtree(output_dir, ignore_errors=True)
        except Exception:
            pass

    return SuccessResponse(message=f"Job {job_id} deleted successfully")


@router.get("/{job_id}/results", response_model=JobResultsResponse)
async def get_job_results(job_id: str, current_user: dict = Depends(require_any_auth)) -> JobResultsResponse:
    """Get results/files for a completed job."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    _check_job_ownership(job, current_user)

    output_dir = job.get("output_dir", "")
    files: List[Dict[str, Any]] = []
    results: Optional[Any] = None

    if output_dir and os.path.isdir(output_dir):
        for root, dirs, fnames in os.walk(output_dir):
            for f in sorted(fnames):
                path = os.path.join(root, f)
                rel = os.path.relpath(path, output_dir)
                size = os.path.getsize(path)
                files.append({
                    "name": rel,
                    "path": path,
                    "size": size,
                    "type": rel.split(".")[-1] if "." in rel else "",
                })

        # Load results.json if exists
        json_path = os.path.join(output_dir, "results.json")
        if os.path.exists(json_path):
            try:
                with open(json_path) as f:
                    data = json.load(f)

                # Try to get extracted content
                if isinstance(data, list) and data:
                    ext = data[0].get("extracted", "")
                    if isinstance(ext, str) and ext:
                        try:
                            results = json.loads(ext)
                        except json.JSONDecodeError:
                            pass
                    elif isinstance(ext, list):
                        results = ext
            except Exception:
                pass

    # Include Vercel Blob URLs if they were stored on the job record
    raw_blob_urls = job.get("blob_urls")
    blob_urls: Optional[Dict[str, str]] = None
    if raw_blob_urls:
        if isinstance(raw_blob_urls, str):
            import json as _json
            try:
                blob_urls = _json.loads(raw_blob_urls)
            except Exception:
                pass
        elif isinstance(raw_blob_urls, dict):
            blob_urls = raw_blob_urls

    return JobResultsResponse(
        job_id=job_id,
        files=files,
        results=results,
        blob_urls=blob_urls,
    )
