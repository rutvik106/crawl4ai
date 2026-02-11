"""SQLite output backend."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List

from crawl4ai.models import CrawlResult


class SQLiteOutput:
    """Store crawl results in a SQLite database."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crawl_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                url TEXT NOT NULL,
                success INTEGER NOT NULL,
                status_code INTEGER,
                error_message TEXT,
                markdown TEXT,
                extracted TEXT
            )
            """
        )
        self.conn.commit()

    def save(self, result: CrawlResult) -> None:
        extracted = result.extracted_content
        if extracted is not None and not isinstance(extracted, str):
            extracted = json.dumps(extracted, ensure_ascii=False)

        self.conn.execute(
            """
            INSERT INTO crawl_results (
                created_at, url, success, status_code, error_message, markdown, extracted
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(),
                result.url,
                1 if result.success else 0,
                result.status_code,
                result.error_message,
                result.markdown.raw_markdown if result.markdown else "",
                extracted,
            ),
        )
        self.conn.commit()

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def latest(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.query(
            "SELECT * FROM crawl_results ORDER BY id DESC LIMIT ?",
            (limit,),
        )

    def stats(self) -> Dict[str, int]:
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS failures
            FROM crawl_results
            """
        ).fetchone()
        assert row is not None
        return {
            "total": int(row["total"] or 0),
            "successes": int(row["successes"] or 0),
            "failures": int(row["failures"] or 0),
        }

    def finalize(self) -> None:
        if getattr(self, "conn", None) is not None:
            self.conn.close()
            self.conn = None
