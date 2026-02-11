"""Helpers to build standard output backends for dashboard jobs."""

from __future__ import annotations

import os
import uuid
from typing import List, Tuple

from .csv_file import CsvFileOutput
from .email_output import EmailOutput
from .html_report import HTMLReportOutput
from .json_file import JsonFileOutput
from .sqlite import SQLiteOutput


def generate_job_id() -> str:
    """Generate a compact unique job identifier."""
    return uuid.uuid4().hex[:12]


def create_job_outputs(
    project_root: str,
    job_id: str,
    title: str,
    email_to: str | None = None,
    smtp_host: str | None = None,
    smtp_port: int = 587,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
    email_subject: str | None = None,
) -> Tuple[str, str, List[object]]:
    """Create default output backend set for a dashboard job."""
    out_dir = os.path.join(project_root, "output", job_id)
    os.makedirs(out_dir, exist_ok=True)

    json_path = os.path.join(out_dir, "results.json")
    report_path = os.path.join(out_dir, "report.html")

    backends: List[object] = [
        JsonFileOutput(path=json_path, append=True),
        CsvFileOutput(path=os.path.join(out_dir, "results.csv")),
        SQLiteOutput(db_path=os.path.join(out_dir, "results.db")),
        HTMLReportOutput(path=report_path, title=title),
    ]

    if email_to and smtp_host:
        backends.append(
            EmailOutput(
                to=email_to,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                smtp_user=smtp_user,
                smtp_password=smtp_password,
                subject=email_subject or f"Crawl4AI: {title}",
            )
        )

    return out_dir, json_path, backends
