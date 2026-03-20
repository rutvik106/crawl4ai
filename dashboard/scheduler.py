"""Background scheduler using APScheduler for recurring crawl jobs."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore

from dashboard import db
from dashboard.engine import run_job_async
from crawl4ai.output.job import generate_job_id

_scheduler: Optional[BackgroundScheduler] = None

# All user-facing cron expressions and internal checks run in IST
_SCHEDULER_TZ = "Asia/Kolkata"


def get_scheduler() -> BackgroundScheduler:
    """Get or create the singleton scheduler instance."""
    global _scheduler
    if _scheduler is None:
        # Use a persistent job store to prevent duplicate jobs
        _scheduler = BackgroundScheduler(
            jobstores={
                'default': MemoryJobStore()
            },
            job_defaults={
                'coalesce': True,  # Combine multiple pending executions
                'max_instances': 1  # Only allow one instance of each job
            }
        )
        _scheduler.start()
        _load_schedules()
    return _scheduler


def _load_schedules() -> None:
    """Load all enabled schedules from DB and register them."""
    schedules = db.list_schedules()
    enabled = [s for s in schedules if s.get("enabled")]
    print(f"[scheduler] Found {len(schedules)} schedules ({len(enabled)} enabled)")
    for sched in enabled:
        _add_schedule_job(sched)
    _register_consolidated_check()
    _register_expiry_check()


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
        trigger = CronTrigger.from_crontab(sched["cron"], timezone=_SCHEDULER_TZ)
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
            print(f"[scheduler] Registered '{sched['job_name']}' cron='{sched['cron']}' next_run={next_run.next_run_time}")
    except Exception as e:
        print(f"[scheduler] Failed to schedule job {sched['job_name']}: {e}")


def _execute_scheduled_job(sched: dict) -> None:
    """Called by APScheduler when a cron trigger fires."""
    print(f"[scheduler] Cron fired for '{sched.get('job_name')}' (schedule_id={sched.get('id')})")
    # Check if schedule still exists and is enabled
    schedule_id = sched.get("id")
    current_schedule = None
    
    try:
        # Get all schedules and find the one with matching ID
        all_schedules = db.list_schedules()
        for s in all_schedules:
            if s.get("id") == schedule_id:
                current_schedule = s
                break
                
        # Skip execution if schedule was deleted or disabled
        if not current_schedule or not current_schedule.get("enabled"):
            print(f"[scheduler] Schedule {schedule_id} was deleted or disabled, skipping execution")
            return
            
        # Use the most up-to-date config
        config = json.loads(current_schedule["config"]) if isinstance(current_schedule["config"], str) else current_schedule["config"]
    except Exception as e:
        print(f"[scheduler] Error checking schedule {schedule_id}: {e}")
        # Fall back to the original config if there was an error
        config = json.loads(sched["config"]) if isinstance(sched["config"], str) else sched["config"]

    # Create a new job entry, linking it to this schedule for consolidated reporting
    job_id = generate_job_id()
    db.create_job(
        job_id=job_id,
        name=f"{sched['job_name']} (scheduled)",
        url=sched["url"],
        config=config,
        schedule_id=sched.get("id"),
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


def _register_consolidated_check() -> None:
    """Register the nightly job that fires consolidated reports when due."""
    scheduler = get_scheduler()
    if scheduler.get_job("consolidated_check"):
        return
    scheduler.add_job(
        _run_consolidated_checks,
        trigger=CronTrigger(hour=23, minute=30, timezone=_SCHEDULER_TZ),
        id="consolidated_check",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    print(f"[scheduler] Registered nightly consolidated check (23:30 IST)")


def _run_consolidated_checks() -> None:
    """Nightly check: fire consolidated reports for weekly/monthly schedules that are due."""
    import zoneinfo
    now = datetime.now(zoneinfo.ZoneInfo(_SCHEDULER_TZ))
    today_weekday = now.weekday()   # Monday=0 … Sunday=6
    is_last_day_of_month = (now + timedelta(days=1)).month != now.month

    schedules = db.list_schedules_with_consolidated()
    print(f"[scheduler] Consolidated check: {len(schedules)} schedule(s) with reports enabled")

    for sched in schedules:
        freq = sched.get("consolidated_frequency")
        last_sent = sched.get("consolidated_last_sent")

        should_send = False
        if freq == "weekly" and today_weekday == 6:   # Sunday
            if last_sent is None or (now - last_sent).days >= 6:
                should_send = True
        elif freq == "monthly" and is_last_day_of_month:
            if last_sent is None or (now - last_sent).days >= 27:
                should_send = True

        if should_send:
            print(f"[scheduler] Triggering consolidated {freq} report for schedule {sched['id']} ({sched.get('job_name')})")
            _dispatch_consolidated_report(sched)


def _dispatch_consolidated_report(sched: dict) -> None:
    """Run consolidated report generation in a background thread."""
    import threading

    def _run():
        from dashboard.consolidated import generate_and_send_consolidated_report
        settings = db.get_all_settings()
        try:
            asyncio.run(generate_and_send_consolidated_report(sched, settings))
        except Exception as e:
            print(f"[scheduler] Consolidated report for schedule {sched['id']} failed: {e}")

    threading.Thread(target=_run, daemon=True).start()


def _register_expiry_check() -> None:
    """Register an hourly job that revokes access for expired users."""
    scheduler = get_scheduler()
    if scheduler.get_job("expiry_check"):
        return
    scheduler.add_job(
        _run_expiry_checks,
        trigger=CronTrigger(minute=0, timezone=_SCHEDULER_TZ),  # top of every hour (IST)
        id="expiry_check",
        replace_existing=True,
        misfire_grace_time=300,
    )
    print("[scheduler] Registered hourly expiry check")


def _run_expiry_checks() -> None:
    """Find users whose access has expired and stop all their resources."""
    expired_users = db.list_expired_users()
    if not expired_users:
        return

    print(f"[scheduler] Expiry check: found {len(expired_users)} expired user(s)")
    scheduler = get_scheduler()

    for user in expired_users:
        user_id = user["id"]
        username = user.get("username", f"id={user_id}")
        print(f"[scheduler] Revoking access for expired user '{username}' (id={user_id})")

        # 1. Disable the account so they can no longer log in
        db.update_user(user_id, is_active=False)

        # 2. Disable all their schedules in DB and remove from APScheduler
        disabled_ids = db.disable_schedules_for_user(user_id)
        for sched_id in disabled_ids:
            job_id = f"schedule_{sched_id}"
            existing = scheduler.get_job(job_id)
            if existing:
                scheduler.remove_job(job_id)
        if disabled_ids:
            print(f"[scheduler] Disabled {len(disabled_ids)} schedule(s) for user '{username}'")

        # 3. Cancel any pending/running jobs
        cancelled = db.cancel_pending_jobs_for_user(user_id)
        if cancelled:
            print(f"[scheduler] Cancelled {cancelled} job(s) for user '{username}'")


def refresh_schedules() -> None:
    """Reload all schedules from DB (call after creating/updating/deleting)."""
    scheduler = get_scheduler()

    # Remove all schedule_ jobs (but keep consolidated_check)
    for job in scheduler.get_jobs():
        if job.id.startswith("schedule_"):
            scheduler.remove_job(job.id)

    # Re-load
    _load_schedules()

    print(f"[scheduler] Refreshed schedules, active jobs: {len(scheduler.get_jobs())}")


def shutdown() -> None:
    """Shut down the scheduler gracefully."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        print("[scheduler] Scheduler shutdown complete")
