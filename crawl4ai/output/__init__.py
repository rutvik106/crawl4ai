"""Output backends for crawl results."""

from .base import OutputManager
from .json_file import JsonFileOutput
from .csv_file import CsvFileOutput
from .sqlite import SQLiteOutput
from .html_report import HTMLReportOutput
from .email_output import EmailOutput
from .webhook_output import WebhookOutput

__all__ = [
    "OutputManager",
    "JsonFileOutput",
    "CsvFileOutput",
    "SQLiteOutput",
    "HTMLReportOutput",
    "EmailOutput",
    "WebhookOutput",
]
