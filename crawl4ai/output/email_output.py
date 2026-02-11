"""Email output backend."""

from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage
from typing import Any, List

from crawl4ai.models import CrawlResult


class EmailOutput:
    """Send crawl summaries by email on finalize."""

    def __init__(
        self,
        to: str,
        smtp_host: str,
        smtp_port: int = 587,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        subject: str = "Crawl4AI results",
        from_email: str | None = None,
    ) -> None:
        self.to = to
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.subject = subject
        self.from_email = from_email or smtp_user or "crawl4ai@localhost"
        self._results: List[CrawlResult] = []

    @staticmethod
    def _parse_extracted(value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # fallback: extract first json array/object inside text blob
                start = min([i for i in [text.find("["), text.find("{")] if i != -1], default=-1)
                if start >= 0:
                    snippet = text[start:]
                    for opener, closer in [("[", "]"), ("{", "}")]:
                        if snippet.startswith(opener):
                            end = snippet.rfind(closer)
                            if end > 0:
                                candidate = snippet[: end + 1]
                                try:
                                    return json.loads(candidate)
                                except json.JSONDecodeError:
                                    pass
                return []
        return []

    def save(self, result: CrawlResult) -> None:
        self._results.append(result)

    def _build_body(self) -> str:
        lines = [f"Total crawl results: {len(self._results)}", ""]
        for idx, result in enumerate(self._results, start=1):
            lines.append(f"{idx}. {result.url} — {'success' if result.success else 'failed'}")
        return "\n".join(lines)

    def finalize(self) -> None:
        if not self._results:
            return
        if not self.to or not self.smtp_host:
            return

        msg = EmailMessage()
        msg["Subject"] = self.subject
        msg["From"] = self.from_email
        msg["To"] = self.to
        msg.set_content(self._build_body())

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            try:
                smtp.starttls()
            except smtplib.SMTPException:
                pass
            if self.smtp_user and self.smtp_password:
                smtp.login(self.smtp_user, self.smtp_password)
            smtp.send_message(msg)
