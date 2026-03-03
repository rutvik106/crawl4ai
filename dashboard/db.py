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

# Track if database has been initialized
_db_initialized = False


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
    global _db_initialized
    if _db_initialized:
        return

    with _conn() as conn:
        cursor = conn.cursor()

        # Create users table first (required before FK references in jobs/schedules)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

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
                output_dir TEXT,
                blob_urls JSONB,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        # Migrations for existing tables that predate these columns
        cursor.execute("""
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS blob_urls JSONB
        """)
        cursor.execute("""
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
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
                created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        # Migration for existing schedules tables
        cursor.execute("""
            ALTER TABLE schedules ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
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

    _db_initialized = True


# ---- Jobs ----

def create_job(
    job_id: str,
    name: str,
    url: str,
    config: Dict[str, Any],
    output_dir: str = "",
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    init_db()  # Ensure DB is initialized
    now = datetime.now()
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO jobs (id, name, url, config, status, created_at, output_dir, user_id)
            VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s)
            """,
            (job_id, name, url, json.dumps(config), now, output_dir, user_id),
        )
    return {"id": job_id, "name": name, "url": url, "status": "pending", "created_at": now.isoformat(), "user_id": user_id}


def update_job(job_id: str, **fields) -> None:
    init_db()  # Ensure DB is initialized
    allowed_fields = {'name', 'url', 'config', 'status', 'started_at', 'finished_at',
                      'article_count', 'error', 'output_dir', 'blob_urls'}

    sets = []
    vals = []
    for k, v in fields.items():
        if k in allowed_fields:
            sets.append(f"{k} = %s")
            if k in ('config', 'blob_urls') and isinstance(v, dict):
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
    init_db()  # Ensure DB is initialized
    with _cursor(RealDictCursor) as cur:
        cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
        row = cur.fetchone()
    if row:
        return dict(row)
    return None


def list_jobs(limit: int = 50, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    init_db()  # Ensure DB is initialized
    with _cursor(RealDictCursor) as cur:
        if user_id is not None:
            cur.execute(
                "SELECT * FROM jobs WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                (user_id, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def delete_job(job_id: str) -> None:
    init_db()  # Ensure DB is initialized
    with _cursor() as cur:
        cur.execute("DELETE FROM jobs WHERE id = %s", (job_id,))


# ---- Schedules ----

def create_schedule(
    job_name: str,
    url: str,
    config: Dict[str, Any],
    cron: str,
    recipients: str,
    user_id: Optional[int] = None,
) -> int:
    init_db()  # Ensure DB is initialized
    now = datetime.now()
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO schedules (job_name, url, config, cron, recipients, created_at, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (job_name, url, json.dumps(config), cron, recipients, now, user_id),
        )
        schedule_id = cur.fetchone()[0]
    return schedule_id


def list_schedules(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    init_db()  # Ensure DB is initialized
    with _cursor(RealDictCursor) as cur:
        if user_id is not None:
            cur.execute(
                "SELECT * FROM schedules WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,),
            )
        else:
            cur.execute("SELECT * FROM schedules ORDER BY created_at DESC")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_schedule_by_id(schedule_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single schedule by its ID."""
    init_db()
    with _cursor(RealDictCursor) as cur:
        cur.execute("SELECT * FROM schedules WHERE id = %s", (schedule_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def update_schedule(schedule_id: int, **fields) -> None:
    init_db()  # Ensure DB is initialized
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
    init_db()  # Ensure DB is initialized
    with _cursor() as cur:
        cur.execute("DELETE FROM schedules WHERE id = %s", (schedule_id,))


# ---- Settings ----

def get_setting(key: str, default: str = "") -> str:
    init_db()  # Ensure DB is initialized
    with _cursor(RealDictCursor) as cur:
        cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
        row = cur.fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    init_db()  # Ensure DB is initialized
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
    init_db()  # Ensure DB is initialized
    with _cursor(RealDictCursor) as cur:
        cur.execute("SELECT key, value FROM settings")
        rows = cur.fetchall()
    return {r["key"]: r["value"] for r in rows}


# ---- Users ----

def create_user(
    username: str,
    password_hash: str,
    role: str = "user",
    email: Optional[str] = None,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Insert a new user record and return it."""
    init_db()
    with _cursor(RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO users (username, email, password_hash, role, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (username, email, password_hash, role, created_by),
        )
        row = cur.fetchone()
    return dict(row)


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Fetch a user by username."""
    init_db()
    with _cursor(RealDictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a user by ID."""
    init_db()
    with _cursor(RealDictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def list_users(created_by: Optional[int] = None) -> List[Dict[str, Any]]:
    """List users, optionally filtered by who created them."""
    init_db()
    with _cursor(RealDictCursor) as cur:
        if created_by is not None:
            cur.execute(
                "SELECT * FROM users WHERE created_by = %s ORDER BY created_at DESC",
                (created_by,),
            )
        else:
            cur.execute("SELECT * FROM users ORDER BY created_at DESC")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def update_user(user_id: int, **fields) -> None:
    """Update allowed fields on a user record."""
    init_db()
    allowed = {"username", "email", "password_hash", "role", "is_active"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = %s")
            vals.append(v)
    if not sets:
        return
    vals.append(user_id)
    with _cursor() as cur:
        cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s", vals)


def upsert_super_admin(username: str, password_hash: str) -> None:
    """Create or update the super-admin account (idempotent on startup)."""
    init_db()
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active)
            VALUES (%s, %s, 'super_admin', TRUE)
            ON CONFLICT (username) DO UPDATE
                SET password_hash = EXCLUDED.password_hash,
                    role = 'super_admin',
                    is_active = TRUE
            """,
            (username, password_hash),
        )


def delete_user(user_id: int) -> None:
    """Delete a user by ID."""
    init_db()
    with _cursor() as cur:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))


# Lazy initialization - init_db() is now called by each function when needed
