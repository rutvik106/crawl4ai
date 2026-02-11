"""Webhook output backend."""

from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib import request

from crawl4ai.models import CrawlResult


class WebhookOutput:
    """POST crawl result payloads to a webhook endpoint."""

    def __init__(self, url: str, headers: Dict[str, str] | None = None, timeout: float = 10.0) -> None:
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self._results: List[CrawlResult] = []

    def save(self, result: CrawlResult) -> None:
        self._results.append(result)

    def _payload(self, result: CrawlResult) -> Dict[str, Any]:
        return {
            "url": result.url,
            "success": result.success,
            "status_code": result.status_code,
            "error_message": result.error_message,
            "extracted_content": result.extracted_content,
        }

    def finalize(self) -> None:
        if not self.url:
            return
        for result in self._results:
            data = json.dumps(self._payload(result)).encode("utf-8")
            req = request.Request(self.url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            for key, value in self.headers.items():
                req.add_header(key, value)
            with request.urlopen(req, timeout=self.timeout):
                pass
