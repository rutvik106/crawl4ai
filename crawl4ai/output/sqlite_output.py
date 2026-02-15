"""SQLite output backend with query support."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import OutputBackend
from ..models import CrawlResult


class SQLiteOutput(OutputBackend):
    """Saves crawl results to a SQLite database.

    Args:
        db_path: Path to the SQLite file. Defaults to ``crawl4ai.db``.
        table: Table name to store results in.

    Query helper::

        db = SQLiteOutput("crawl4ai.db")
        rows = db.query("SELECT url, extracted FROM crawl_results WHERE success = 1")
        latest = db.latest(5)
    """

    def __init__(self, db_path: str = "crawl4ai.db", table: str = "crawl_results") -> None:
        self.db_path = db_path
        self.table = table
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                status_code INTEGER,
                timestamp TEXT NOT NULL,
                markdown TEXT,
                markdown_length INTEGER,
                extracted TEXT,
                error TEXT,
                metadata TEXT
            )
        """)
        self._conn.commit()

    def save(self, result: CrawlResult, metadata: Optional[Dict[str, Any]] = None) -> None:
        extracted = result.extracted_content or ""
        meta_json = json.dumps(metadata) if metadata else None

        self._conn.execute(
            f"""INSERT INTO {self.table}
                (url, success, status_code, timestamp, markdown, markdown_length, extracted, error, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.url,
                result.success,
                result.status_code,
                datetime.now().isoformat(),
                result.markdown.raw_markdown,
                len(result.markdown.raw_markdown),
                extracted,
                result.error_message,
                meta_json,
            ),
        )
        self._conn.commit()

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Run a custom SQL query and return rows as dicts."""
        cursor = self._conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def latest(self, n: int = 10) -> List[Dict[str, Any]]:
        """Return the N most recent results."""
        return self.query(
            f"SELECT * FROM {self.table} ORDER BY id DESC LIMIT ?", (n,)
        )

    def stats(self) -> Dict[str, Any]:
        """Return summary statistics about stored crawl results."""
        row = self._conn.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failures,
                AVG(markdown_length) as avg_markdown_length,
                MIN(timestamp) as first_crawl,
                MAX(timestamp) as last_crawl
            FROM {self.table}
        """).fetchone()
        return dict(row)

    def finalize(self) -> None:
        self._conn.close()
