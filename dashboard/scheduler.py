"""Background scheduler using APScheduler for recurring crawl jobs."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from dashboard import db
from dashboard.engine import run_job_async
from crawl4ai.output.job import generate_job_id

_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> BackgroundScheduler:
    """Get or create the singleton scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        _scheduler.start()
        _load_schedules()
    return _scheduler


def _load_schedules() -> None:
    """Load all enabled schedules from DB and register them."""
    schedules = db.list_schedules()
    for sched in schedules:
        if sched.get("enabled"):
            _add_schedule_job(sched)


def _add_schedule_job(sched: dict) -> None:
    """Add a single schedule to APScheduler."""
    scheduler = get_scheduler()
    job_id = f"schedule_{sched['id']}"

    # Remove existing if any
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)

    if not sched.get("enabled"):
        return

    try:
        trigger = CronTrigger.from_crontab(sched["cron"])
        scheduler.add_job(
            _execute_scheduled_job,
            trigger=trigger,
            id=job_id,
            args=[sched],
            replace_existing=True,
            misfire_grace_time=300,
        )

        # Update next run time
        next_run = scheduler.get_job(job_id)
        if next_run and next_run.next_run_time:
            db.update_schedule(
                sched["id"],
                next_run=next_run.next_run_time.isoformat(),
            )
    except Exception as e:
        print(f"Failed to schedule job {sched['job_name']}: {e}")


def _execute_scheduled_job(sched: dict) -> None:
    """Called by APScheduler when a cron trigger fires."""
    config = json.loads(sched["config"]) if isinstance(sched["config"], str) else sched["config"]

    # Create a new job entry
    job_id = generate_job_id()
    db.create_job(
        job_id=job_id,
        name=f"{sched['job_name']} (scheduled)",
        url=sched["url"],
        config=config,
    )

    # Update last_run
    db.update_schedule(sched["id"], last_run=datetime.now().isoformat())

    # Update next run
    scheduler = get_scheduler()
    ap_job = scheduler.get_job(f"schedule_{sched['id']}")
    if ap_job and ap_job.next_run_time:
        db.update_schedule(sched["id"], next_run=ap_job.next_run_time.isoformat())

    # Execute
    run_job_async(job_id)


def refresh_schedules() -> None:
    """Reload all schedules from DB (call after creating/updating/deleting)."""
    scheduler = get_scheduler()

    # Remove all schedule_ jobs
    for job in scheduler.get_jobs():
        if job.id.startswith("schedule_"):
            scheduler.remove_job(job.id)

    # Re-load
    _load_schedules()


def shutdown() -> None:
    """Shut down the scheduler gracefully."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
