"""JSON file output backend."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from crawl4ai.models import CrawlResult


def _parse_extracted_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return value
    return value


class JsonFileOutput:
    """Persist crawl results as a JSON list."""

    def __init__(self, path: str, append: bool = True) -> None:
        self.path = path
        self.append = append
        self._initialized = False

    def _serialize(self, result: CrawlResult) -> Dict[str, Any]:
        return {
            "url": result.url,
            "success": result.success,
            "status_code": result.status_code,
            "error_message": result.error_message,
            "markdown": result.markdown.raw_markdown if result.markdown else "",
            "extracted": _parse_extracted_value(result.extracted_content),
            "metadata": result.metadata,
        }

    def save(self, result: CrawlResult) -> None:
        record = self._serialize(result)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

        records: List[Dict[str, Any]] = []
        should_read_existing = self.append or self._initialized
        if should_read_existing and os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as infile:
                try:
                    existing = json.load(infile)
                    if isinstance(existing, list):
                        records = existing
                except json.JSONDecodeError:
                    records = []

        records.append(record)
        with open(self.path, "w", encoding="utf-8") as outfile:
            json.dump(records, outfile, indent=2, ensure_ascii=False)

        self._initialized = True

    def finalize(self) -> None:
        return None
