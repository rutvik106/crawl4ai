"""Job-related output utilities for Crawl4AI."""

import os
import uuid
from typing import Any, Dict, List, Optional

from . import (
    OutputManager,
    JsonFileOutput,
    HTMLReportOutput,
    EmailOutput,
)


def generate_job_id() -> str:
    """Generate a unique job ID."""
    return str(uuid.uuid4())


def create_job_outputs(
    project_root: str,
    job_id: str,
    title: str = "Crawl4AI Report",
    email_to: Optional[str] = None,
    smtp_host: Optional[str] = None,
    smtp_port: int = 587,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
    email_subject: Optional[str] = None,
):
    """Create output backends for a job based on configuration.

    Returns:
        Tuple of (json_path, html_path, list_of_backends).
    """
    output_dir = os.path.join(project_root, "output", job_id)
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, "results.json")
    html_path = os.path.join(output_dir, "report.html")

    backends: List = [
        JsonFileOutput(path=json_path, append=False),
        HTMLReportOutput(path=html_path, title=title),
    ]

    if email_to and smtp_host and smtp_user and smtp_password:
        to_list = [e.strip() for e in email_to.split(",") if e.strip()]
        if to_list:
            backends.append(
                EmailOutput(
                    smtp_host=smtp_host,
                    smtp_port=smtp_port,
                    smtp_user=smtp_user,
                    smtp_password=smtp_password,
                    to_emails=to_list,
                )
            )

    return json_path, html_path, backends
