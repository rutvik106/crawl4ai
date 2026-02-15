"""Webhook output backend — POSTs crawl results to any URL."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen

from .base import OutputBackend
from ..models import CrawlResult


class WebhookOutput(OutputBackend):
    """POSTs each crawl result to a webhook URL as JSON.

    Works with Slack incoming webhooks, Discord webhooks,
    Zapier, Make, n8n, or any custom endpoint.

    Args:
        url: The webhook URL to POST to.
        headers: Extra HTTP headers (e.g. Authorization).
        format: "raw" sends the full result; "slack" formats for Slack.
    """

    def __init__(
        self,
        url: str = "",
        headers: Optional[Dict[str, str]] = None,
        format: str = "raw",
    ) -> None:
        self.url = url
        self.headers = headers or {}
        self.format = format

    def save(self, result: CrawlResult, metadata: Optional[Dict[str, Any]] = None) -> None:
        if not self.url:
            return

        if self.format == "slack":
            payload = self._format_slack(result)
        else:
            payload = self._format_raw(result, metadata)

        data = json.dumps(payload).encode("utf-8")
        req_headers = {"Content-Type": "application/json", **self.headers}
        req = Request(self.url, data=data, headers=req_headers, method="POST")

        try:
            urlopen(req, timeout=10)
        except Exception:
            pass  # Best-effort; don't break the crawl pipeline

    def _format_raw(self, result: CrawlResult, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "url": result.url,
            "success": result.success,
            "status_code": result.status_code,
            "timestamp": datetime.now().isoformat(),
            "markdown_length": len(result.markdown.raw_markdown),
        }
        if result.extracted_content:
            try:
                payload["extracted"] = json.loads(result.extracted_content)
            except (json.JSONDecodeError, TypeError):
                payload["extracted"] = result.extracted_content
        if result.error_message:
            payload["error"] = result.error_message
        if metadata:
            payload["metadata"] = metadata
        return payload

    def _format_slack(self, result: CrawlResult) -> Dict[str, Any]:
        status = ":white_check_mark:" if result.success else ":x:"
        text = f"{status} *{result.url}*\n"
        text += f"Markdown: {len(result.markdown.raw_markdown)} chars"

        if result.extracted_content:
            try:
                items = json.loads(result.extracted_content)
                if isinstance(items, list):
                    text += f" | Extracted: {len(items)} items"
            except (json.JSONDecodeError, TypeError):
                pass

        if result.error_message:
            text += f"\n:warning: Error: {result.error_message}"

        return {"text": text}
