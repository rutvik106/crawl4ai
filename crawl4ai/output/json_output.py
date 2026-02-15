"""JSON file output backend."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import OutputBackend
from ..models import CrawlResult


class JsonFileOutput(OutputBackend):
    """Saves crawl results to a JSON file.

    Args:
        path: Output file path. Defaults to ``crawl_results.json``.
        append: If True, appends to existing file; otherwise overwrites.
        indent: JSON indentation level.
    """

    def __init__(self, path: str = "crawl_results.json", append: bool = True, indent: int = 2) -> None:
        self.path = path
        self.append = append
        self.indent = indent
        self._results: List[Dict[str, Any]] = []

        if append and os.path.exists(path):
            with open(path, "r") as f:
                try:
                    self._results = json.load(f)
                except json.JSONDecodeError:
                    self._results = []

    def save(self, result: CrawlResult, metadata: Optional[Dict[str, Any]] = None) -> None:
        entry = self._serialize(result, metadata)
        self._results.append(entry)
        self._flush()

    def _serialize(self, result: CrawlResult, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "url": result.url,
            "success": result.success,
            "status_code": result.status_code,
            "timestamp": datetime.now().isoformat(),
            "markdown_length": len(result.markdown.raw_markdown),
            "markdown": result.markdown.raw_markdown,
        }
        if result.extracted_content:
            try:
                entry["extracted"] = json.loads(result.extracted_content)
            except (json.JSONDecodeError, TypeError):
                entry["extracted"] = result.extracted_content
        if result.error_message:
            entry["error"] = result.error_message
        if metadata:
            entry["metadata"] = metadata
        return entry

    def _flush(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self._results, f, indent=self.indent, ensure_ascii=False)
