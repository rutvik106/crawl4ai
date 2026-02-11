"""CSV output backend."""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict

from crawl4ai.models import CrawlResult


class CsvFileOutput:
    """Persist crawl results into a flat CSV file."""

    FIELDNAMES = [
        "url",
        "success",
        "status_code",
        "error_message",
        "markdown",
        "extracted",
    ]

    def __init__(self, path: str) -> None:
        self.path = path

    def _serialize(self, result: CrawlResult) -> Dict[str, Any]:
        extracted = result.extracted_content
        if not isinstance(extracted, str):
            extracted = json.dumps(extracted) if extracted is not None else ""

        return {
            "url": result.url,
            "success": result.success,
            "status_code": result.status_code,
            "error_message": result.error_message or "",
            "markdown": result.markdown.raw_markdown if result.markdown else "",
            "extracted": extracted,
        }

    def save(self, result: CrawlResult) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        file_exists = os.path.exists(self.path)
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow(self._serialize(result))

    def finalize(self) -> None:
        return None
