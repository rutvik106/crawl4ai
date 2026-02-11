"""Output backends for Crawl4AI results."""

import csv
import json
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models import CrawlResult


class OutputBackend(ABC):
    """Abstract base class for output backends."""

    @abstractmethod
    def save(self, result: CrawlResult) -> None:
        pass

    def finalize(self) -> None:
        pass


class JsonFileOutput(OutputBackend):
    """Output backend that saves results to a JSON file."""

    def __init__(self, path: str, append: bool = True):
        self.path = path
        self.append = append
        self._data: list = []
        if append and os.path.exists(path):
            try:
                with open(path, "r") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                self._data = []

    def save(self, result: CrawlResult) -> None:
        data = {
            "url": result.url,
            "success": result.success,
            "status_code": result.status_code,
            "html": result.html,
            "markdown": {
                "raw_markdown": result.markdown.raw_markdown,
                "fit_markdown": result.markdown.fit_markdown,
            },
            "extracted": result.extracted_content,
            "error_message": result.error_message,
            "timestamp": datetime.now().isoformat(),
        }
        self._data.append(data)
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2)


class CsvFileOutput(OutputBackend):
    """Output backend that saves results to a CSV file."""

    def __init__(self, path: str):
        self.path = path
        self._headers_written = False

    def save(self, result: CrawlResult) -> None:
        file_exists = os.path.exists(self.path)
        with open(self.path, "a", newline="") as f:
            fieldnames = (
                "url",
                "success",
                "status_code",
                "error_message",
                "markdown_length",
                "extracted_content",
                "timestamp",
            )
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not self._headers_written and not file_exists:
                writer.writeheader()
                self._headers_written = True
            writer.writerow(
                {
                    "url": result.url,
                    "success": result.success,
                    "status_code": result.status_code,
                    "error_message": result.error_message,
                    "markdown_length": len(result.markdown.raw_markdown)
                    if result.markdown.raw_markdown
                    else 0,
                    "extracted_content": result.extracted_content,
                    "timestamp": datetime.now().isoformat(),
                }
            )


class SQLiteOutput(OutputBackend):
    """Output backend that saves results to an SQLite database."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
                CREATE TABLE IF NOT EXISTS crawl_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    status_code INTEGER,
                    html TEXT,
                    markdown_raw TEXT,
                    markdown_fit TEXT,
                    extracted_content TEXT,
                    error_message TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
        )
        conn.commit()

    def save(self, result: CrawlResult) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
                INSERT INTO crawl_results
                (url, success, status_code, html, markdown_raw, markdown_fit, extracted_content, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.url,
                result.success,
                result.status_code,
                result.html,
                result.markdown.raw_markdown,
                result.markdown.fit_markdown,
                result.extracted_content,
                result.error_message,
            ),
        )
        conn.commit()

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def latest(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.query(
            "SELECT * FROM crawl_results ORDER BY timestamp DESC LIMIT ?", (limit,)
        )

    def stats(self) -> Dict[str, Any]:
        return self.query(
            """
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN success = 1 THEN 1 END) as successes,
                COUNT(CASE WHEN success = 0 THEN 1 END) as failures
            FROM crawl_results
        """
        )[0]

    def finalize(self) -> None:
        pass


class HTMLReportOutput(OutputBackend):
    """Output backend that generates an HTML report."""

    def __init__(self, path: str, title: str = "Crawl4AI Report"):
        self.path = path
        self.title = title
        self.results = []

    def save(self, result: CrawlResult) -> None:
        self.results.append(result)

    def finalize(self):
        title = self.title
        generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total = len(self.results)
        html_parts = []
        html_parts.append(
            "<!DOCTYPE html>\n<html><head><title>"
            + title
            + """</title>
<style>
body { font-family: Arial, sans-serif; margin: 20px; }
.result { border: 1px solid #ddd; margin: 10px 0; padding: 15px; }
.success { border-left: 5px solid #4CAF50; }
.failure { border-left: 5px solid #f44336; }
.url { font-weight: bold; color: #2196F3; }
pre { white-space: pre-wrap; background: #f5f5f5; padding: 10px; }
</style></head><body>
<h1>"""
            + title
            + "</h1>\n<p>Generated: "
            + generated
            + " | Total: "
            + str(total)
            + "</p>\n"
        )
        for result in self.results:
            cls = "success" if result.success else "failure"
            md = result.markdown.raw_markdown or ""
            if len(md) > 500:
                md = md[:500] + "..."
            error_html = ""
            if result.error_message:
                error_html = "<p>Error: " + result.error_message + "</p>"
            html_parts.append(
                '<div class="result '
                + cls
                + '"><div class="url">'
                + result.url
                + "</div>"
                + "<pre>"
                + md
                + "</pre>"
                + error_html
                + "</div>\n"
            )
        html_parts.append("</body></html>")
        with open(self.path, "w") as f:
            f.write("".join(html_parts))


class EmailOutput(OutputBackend):
    """Output backend that sends results via email."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        to_emails: List[str],
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.to_emails = to_emails
        self.results = []

    def save(self, result: CrawlResult) -> None:
        self.results.append(result)

    def finalize(self):
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        body_parts = []
        for result in self.results:
            status = "SUCCESS" if result.success else "FAILED"
            body_parts.append(
                status
                + ": "
                + result.url
                + " (Status: "
                + str(result.status_code)
                + ")\n"
            )
            if result.error_message:
                body_parts.append("  Error: " + result.error_message + "\n")

        msg = MIMEMultipart()
        msg["From"] = self.smtp_user
        msg["To"] = ", ".join(self.to_emails)
        msg["Subject"] = (
            "Crawl4AI Results - " + datetime.now().strftime("%Y-%m-%d")
        )
        msg.attach(MIMEText("\n".join(body_parts), "plain"))

        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)
        except Exception as e:
            print("Failed to send email: " + str(e))


class WebhookOutput(OutputBackend):
    """Output backend that sends results to a webhook URL."""

    def __init__(self, webhook_url: str, headers: Optional[Dict] = None):
        self.webhook_url = webhook_url
        self.headers = headers or {"Content-Type": "application/json"}

    def save(self, result: CrawlResult) -> None:
        data = {
            "url": result.url,
            "success": result.success,
            "status_code": result.status_code,
            "extracted": result.extracted_content,
            "error_message": result.error_message,
            "timestamp": datetime.now().isoformat(),
        }
        try:
            if isinstance(data["extracted"], str):
                data["extracted"] = json.loads(data["extracted"])
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            import requests

            requests.post(
                self.webhook_url, json=data, headers=self.headers, timeout=30
            )
        except Exception as e:
            print("Failed to send webhook: " + str(e))


class OutputManager:
    """Manager that dispatches results to multiple output backends."""

    def __init__(self, backends: List[OutputBackend]):
        self.backends = backends

    def save(self, result: CrawlResult) -> None:
        for backend in self.backends:
            backend.save(result)

    def save_many(self, results: List[CrawlResult]) -> None:
        for result in results:
            self.save(result)

    def finalize(self) -> None:
        for backend in self.backends:
            backend.finalize()
