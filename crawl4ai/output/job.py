"""Job-based output directory management.

Auto-generates a unique job folder for each crawl run under the project's
``output/`` directory.

Usage::

    from crawl4ai.output.job import create_job_outputs

    outputs = create_job_outputs(
        email_to="user@example.com",
        smtp_host="smtp.zoho.in",
        ...
    )
    # Creates: output/20260207_210500_a3f2/
    #   ├── results.json
    #   ├── results.csv
    #   ├── crawls.db
    #   └── report.html
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import OutputBackend
from .json_output import JsonFileOutput
from .csv_output import CsvFileOutput
from .sqlite_output import SQLiteOutput
from .html_report import HTMLReportOutput
from .email_output import EmailOutput


def generate_job_id() -> str:
    """Generate a unique job ID: YYYYMMDD_HHMMSS_<short-uuid>."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    return f"{ts}_{short_id}"


def create_job_outputs(
    project_root: str = "",
    job_id: Optional[str] = None,
    title: str = "Crawl4AI Report",
    email_to: Optional[str] = None,
    smtp_host: Optional[str] = None,
    smtp_port: int = 587,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
    smtp_from: Optional[str] = None,
    email_subject: Optional[str] = None,
) -> tuple:
    """Create a full set of output backends under ``output/<job_id>/``.

    Returns:
        (job_id, job_dir, list_of_backends)
    """
    if not project_root:
        project_root = os.getcwd()

    if not job_id:
        job_id = generate_job_id()

    job_dir = os.path.join(project_root, "output", job_id)
    os.makedirs(job_dir, exist_ok=True)

    backends: List[OutputBackend] = [
        JsonFileOutput(path=os.path.join(job_dir, "results.json"), append=False),
        CsvFileOutput(path=os.path.join(job_dir, "results.csv")),
        SQLiteOutput(db_path=os.path.join(job_dir, "crawls.db")),
        HTMLReportOutput(path=os.path.join(job_dir, "report.html"), title=title),
    ]

    if email_to and smtp_host:
        backends.append(EmailOutput(
            to=email_to,
            subject=email_subject or f"Crawl4AI: {title}",
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user or "",
            smtp_password=smtp_password or "",
            from_addr=smtp_from or smtp_user or "",
        ))

    return job_id, job_dir, backends
