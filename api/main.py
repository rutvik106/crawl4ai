"""FastAPI main application for Crawl4AI.

This module provides REST API endpoints for managing crawl jobs,
schedules, settings, and retrieving dashboard statistics.

To run the API server:
    uvicorn api.main:app --reload --port 8000

Or using Python directly:
    python -m uvicorn api.main:app --reload --port 8000
"""

import os
import sys

# Ensure project root is on the path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dashboard.scheduler import get_scheduler, shutdown as scheduler_shutdown
from dashboard import db
from dashboard.log_buffer import attach_to_root_logger
from api.auth import hash_password
from api.routers import jobs, schedules, settings, stats
from api.routers import auth as auth_router
from api.routers import users as users_router
from api.routers import logs as logs_router

# Attach in-memory log buffer as early as possible
attach_to_root_logger()


def _seed_super_admin() -> None:
    """Create or refresh the super-admin account from environment variables."""
    username = os.getenv("SUPER_ADMIN_USERNAME", "superadmin")
    password = os.getenv("SUPER_ADMIN_PASSWORD", "SuperAdmin123!")
    db.upsert_super_admin(username, hash_password(password))
    print(f"[api] Super-admin account ready (username: {username})")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - start scheduler on startup, cleanup on shutdown."""
    print("[api] Starting up...")
    get_scheduler()
    print("[api] Scheduler initialized and running")
    try:
        _seed_super_admin()
    except Exception as e:
        print(f"[api] Warning: could not seed super-admin: {e}")
    yield
    print("[api] Shutting down...")
    scheduler_shutdown()


# Create FastAPI app with lifespan manager
app = FastAPI(
    title="Crawl4AI API",
    description="REST API for web crawling and job management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers with /api prefix
app.include_router(auth_router.router, prefix="/api")
app.include_router(users_router.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(schedules.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(logs_router.router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint with API info."""
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
        },
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
