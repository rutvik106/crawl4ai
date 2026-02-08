"""SQLite persistence for jobs, schedules, and settings."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


DB_PATH = os.path.join(os.path.dirname(__file__), "crawl4ai_dashboard.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            config JSON NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            article_count INTEGER DEFAULT 0,
            error TEXT,
            output_dir TEXT
        );

        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT NOT NULL,
            url TEXT NOT NULL,
            config JSON NOT NULL,
            cron TEXT NOT NULL,
            recipients TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            last_run TEXT,
            next_run TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# ---- Jobs ----

def create_job(
    job_id: str,
    name: str,
    url: str,
    config: Dict[str, Any],
    output_dir: str = "",
) -> Dict[str, Any]:
    conn = _conn()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO jobs (id, name, url, config, status, created_at, output_dir) "
        "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
        (job_id, name, url, json.dumps(config), now, output_dir),
    )
    conn.commit()
    conn.close()
    return {"id": job_id, "name": name, "url": url, "status": "pending", "created_at": now}


def update_job(job_id: str, **fields) -> None:
    conn = _conn()
    sets = []
    vals = []
    for k, v in fields.items():
        sets.append(f"{k} = ?")
        vals.append(v)
    vals.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    conn = _conn()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def list_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_job(job_id: str) -> None:
    conn = _conn()
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()


# ---- Schedules ----

def create_schedule(
    job_name: str,
    url: str,
    config: Dict[str, Any],
    cron: str,
    recipients: str,
) -> int:
    conn = _conn()
    now = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO schedules (job_name, url, config, cron, recipients, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (job_name, url, json.dumps(config), cron, recipients, now),
    )
    conn.commit()
    schedule_id = cur.lastrowid
    conn.close()
    return schedule_id


def list_schedules() -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute("SELECT * FROM schedules ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_schedule(schedule_id: int, **fields) -> None:
    conn = _conn()
    sets = []
    vals = []
    for k, v in fields.items():
        sets.append(f"{k} = ?")
        vals.append(v)
    vals.append(schedule_id)
    conn.execute(f"UPDATE schedules SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def delete_schedule(schedule_id: int) -> None:
    conn = _conn()
    conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()


# ---- Settings ----

def get_setting(key: str, default: str = "") -> str:
    conn = _conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_all_settings() -> Dict[str, str]:
    conn = _conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# Auto-init on import
init_db()
