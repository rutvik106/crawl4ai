"""Pluggable output backends for crawl results."""

from .base import OutputBackend, OutputManager
from .json_output import JsonFileOutput
from .csv_output import CsvFileOutput
from .sqlite_output import SQLiteOutput
from .html_report import HTMLReportOutput
from .email_output import EmailOutput
from .webhook_output import WebhookOutput
from .pdf_output import PDFReportOutput
from .job import create_job_outputs, generate_job_id

__all__ = [
    "OutputBackend",
    "OutputManager",
    "JsonFileOutput",
    "CsvFileOutput",
    "SQLiteOutput",
    "HTMLReportOutput",
    "EmailOutput",
    "WebhookOutput",
    "PDFReportOutput",
    "create_job_outputs",
    "generate_job_id",
]
