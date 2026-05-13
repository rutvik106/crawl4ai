"""FastAPI main application for Crawl4AI.

To run the API server:
    uvicorn api.main:app --reload --port 8000
"""

import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dashboard.scheduler import get_scheduler, shutdown as scheduler_shutdown
from dashboard import db
from dashboard.engine import run_job_async
from dashboard.log_buffer import attach_to_root_logger
from api.auth import hash_password
from api.routers import jobs, schedules, settings, stats
from api.routers import auth as auth_router
from api.routers import users as users_router
from api.routers import logs as logs_router
from api.routers import intelligence as intelligence_router

attach_to_root_logger()


def _seed_super_admin() -> None:
    username = os.getenv("SUPER_ADMIN_USERNAME", "superadmin")
    password = os.getenv("SUPER_ADMIN_PASSWORD", "SuperAdmin123!")
    db.upsert_super_admin(username, hash_password(password))
    print(f"[api] Super-admin account ready (username: {username})")


def _recover_unfinished_jobs() -> None:
    try:
        unfinished = db.get_unfinished_jobs()
        if not unfinished:
            return
        pending = [j for j in unfinished if j["status"] == "pending"]
        interrupted = [j for j in unfinished if j["status"] == "running"]
        for job in interrupted:
            db.update_job(
                job["id"],
                status="failed",
                error="Job was interrupted by a server restart and could not be resumed.",
            )
            print(f"[api] Marked interrupted job {job['id']} ({job['name']!r}) as failed")
        for job in pending:
            run_job_async(job["id"])
            print(f"[api] Re-queued pending job {job['id']} ({job['name']!r})")
        if interrupted or pending:
            print(
                f"[api] Startup recovery: {len(interrupted)} interrupted job(s) marked failed, "
                f"{len(pending)} pending job(s) re-queued"
            )
    except Exception as exc:
        print(f"[api] Warning: startup job recovery failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[api] Starting up...")
    get_scheduler()
    print("[api] Scheduler initialized and running")
    try:
        _seed_super_admin()
    except Exception as e:
        print(f"[api] Warning: could not seed super-admin: {e}")
    _recover_unfinished_jobs()
    yield
    print("[api] Shutting down...")
    scheduler_shutdown()


app = FastAPI(
    title="Crawl4AI API",
    description="REST API for web crawling and job management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/api")
app.include_router(users_router.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(schedules.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(logs_router.router, prefix="/api")
app.include_router(intelligence_router.router, prefix="/api")


@app.get("/")
async def root():
    return {
        "message": "Crawl4AI API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "auth": "/api/auth",
            "users": "/api/users",
            "jobs": "/api/jobs",
            "schedules": "/api/schedules",
            "settings": "/api/settings",
            "stats": "/api/stats",
            "logs": "/api/logs",
            "intelligence": "/api/intelligence",
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
