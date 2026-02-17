"""PostgreSQL persistence for jobs, schedules, and settings (Neon.tech compatible)."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Load environment variables from .env file
load_dotenv()

# Neon.tech connection string from environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/crawl4ai_dashboard"  # fallback for local dev
)


@contextmanager
def _conn():
    """Context manager for database connections."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _cursor(cursor_factory=None):
    """Context manager for database cursors."""
    with _conn() as conn:
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()


def init_db() -> None:
    """Create tables if they don't exist."""
    with _conn() as conn:
        cursor = conn.cursor()

        # Create jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                config JSONB NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                started_at TIMESTAMP WITH TIME ZONE,
                finished_at TIMESTAMP WITH TIME ZONE,
                article_count INTEGER DEFAULT 0,
                error TEXT,
                output_dir TEXT
            )
        """)

        # Create schedules table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id SERIAL PRIMARY KEY,
                job_name TEXT NOT NULL,
                url TEXT NOT NULL,
                config JSONB NOT NULL,
                cron TEXT NOT NULL,
                recipients TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                last_run TIMESTAMP WITH TIME ZONE,
                next_run TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL
            )
        """)

        # Create settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        conn.commit()
        cursor.close()


# ---- Jobs ----

def create_job(
    job_id: str,
    name: str,
    url: str,
    config: Dict[str, Any],
    output_dir: str = "",
) -> Dict[str, Any]:
    now = datetime.now()
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO jobs (id, name, url, config, status, created_at, output_dir)
            VALUES (%s, %s, %s, %s, 'pending', %s, %s)
            """,
            (job_id, name, url, json.dumps(config), now, output_dir),
        )
    return {"id": job_id, "name": name, "url": url, "status": "pending", "created_at": now.isoformat()}


def update_job(job_id: str, **fields) -> None:
    allowed_fields = {'name', 'url', 'config', 'status', 'started_at', 'finished_at',
                      'article_count', 'error', 'output_dir'}

    sets = []
    vals = []
    for k, v in fields.items():
        if k in allowed_fields:
            sets.append(f"{k} = %s")
            if k == 'config' and isinstance(v, dict):
                vals.append(json.dumps(v))
            elif k in ('started_at', 'finished_at') and v is not None:
                vals.append(v if isinstance(v, datetime) else datetime.fromisoformat(v))
            else:
                vals.append(v)

    if not sets:
        return

    vals.append(job_id)
    with _cursor() as cur:
        cur.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = %s", vals)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _cursor(RealDictCursor) as cur:
        cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
        row = cur.fetchone()
    if row:
        return dict(row)
    return None


def list_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    with _cursor(RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT %s",
            (limit,)
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def delete_job(job_id: str) -> None:
    with _cursor() as cur:
        cur.execute("DELETE FROM jobs WHERE id = %s", (job_id,))


# ---- Schedules ----

def create_schedule(
    job_name: str,
    url: str,
    config: Dict[str, Any],
    cron: str,
    recipients: str,
) -> int:
    now = datetime.now()
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO schedules (job_name, url, config, cron, recipients, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (job_name, url, json.dumps(config), cron, recipients, now),
        )
        schedule_id = cur.fetchone()[0]
    return schedule_id


def list_schedules() -> List[Dict[str, Any]]:
    with _cursor(RealDictCursor) as cur:
        cur.execute("SELECT * FROM schedules ORDER BY created_at DESC")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def update_schedule(schedule_id: int, **fields) -> None:
    allowed_fields = {'job_name', 'url', 'config', 'cron', 'recipients',
                      'enabled', 'last_run', 'next_run'}

    sets = []
    vals = []
    for k, v in fields.items():
        if k in allowed_fields:
            sets.append(f"{k} = %s")
            if k == 'config' and isinstance(v, dict):
                vals.append(json.dumps(v))
            elif k in ('last_run', 'next_run') and v is not None:
                vals.append(v if isinstance(v, datetime) else datetime.fromisoformat(v))
            else:
                vals.append(v)

    if not sets:
        return

    vals.append(schedule_id)
    with _cursor() as cur:
        cur.execute(f"UPDATE schedules SET {', '.join(sets)} WHERE id = %s", vals)


def delete_schedule(schedule_id: int) -> None:
    with _cursor() as cur:
        cur.execute("DELETE FROM schedules WHERE id = %s", (schedule_id,))


# ---- Settings ----

def get_setting(key: str, default: str = "") -> str:
    with _cursor(RealDictCursor) as cur:
        cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
        row = cur.fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, value),
        )


def get_all_settings() -> Dict[str, str]:
    with _cursor(RealDictCursor) as cur:
        cur.execute("SELECT key, value FROM settings")
        rows = cur.fetchall()
    return {r["key"]: r["value"] for r in rows}


# Auto-init on import
init_db()
