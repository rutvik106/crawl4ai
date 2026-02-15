"""CSV file output backend."""

from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Any, Dict, Optional

from .base import OutputBackend
from ..models import CrawlResult


class CsvFileOutput(OutputBackend):
    """Saves crawl results to a CSV file.

    Args:
        path: Output file path. Defaults to ``crawl_results.csv``.
        include_markdown: Whether to include the full markdown in the CSV.
    """

    _FIELDS = ["timestamp", "url", "success", "status_code", "markdown_length", "extracted_content", "error"]
    _FIELDS_WITH_MD = _FIELDS + ["markdown"]

    def __init__(self, path: str = "crawl_results.csv", include_markdown: bool = False) -> None:
        self.path = path
        self.include_markdown = include_markdown
        self._fields = self._FIELDS_WITH_MD if include_markdown else self._FIELDS
        self._file_exists = os.path.exists(path)

    def save(self, result: CrawlResult, metadata: Optional[Dict[str, Any]] = None) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        write_header = not self._file_exists

        with open(self.path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._fields, extrasaction="ignore")
            if write_header:
                writer.writeheader()
                self._file_exists = True

            row = {
                "timestamp": datetime.now().isoformat(),
                "url": result.url,
                "success": result.success,
                "status_code": result.status_code,
                "markdown_length": len(result.markdown.raw_markdown),
                "extracted_content": result.extracted_content or "",
                "error": result.error_message or "",
            }
            if self.include_markdown:
                row["markdown"] = result.markdown.raw_markdown

            writer.writerow(row)
