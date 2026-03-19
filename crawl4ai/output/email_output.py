"""Email output backend — sends crawl results via HTTP API."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

# IST = UTC+5:30
_IST = timezone(timedelta(hours=5, minutes=30))

from .base import OutputBackend
from ..models import CrawlResult

EMAIL_API_URL = "https://time-tracker-3-sigma.vercel.app/api/v1/users/emailsend"


class EmailOutput(OutputBackend):
    """Sends crawl results as an HTML email via the email HTTP API.

    Results are accumulated and sent as a single email on ``finalize()``.

    Args:
        to: Recipient email address(es), comma-separated.
        subject: Email subject line.
        ai_summary: Optional AI-generated summary to include in the email.

    Usage::

        output = EmailOutput(
            to="you@email.com",
            subject="Daily News Crawl",
        )
    """

    def __init__(
        self,
        to: str = "",
        subject: str = "Crawl4AI Results",
        ai_summary: str = "",
    ) -> None:
        self.to = to
        self.subject = subject
        self.ai_summary = ai_summary
        self._results: List[Dict[str, Any]] = []

    def save(self, result: CrawlResult, metadata: Optional[Dict[str, Any]] = None) -> None:
        entry: Dict[str, Any] = {
            "url": result.url,
            "success": result.success,
            "markdown_length": len(result.markdown.raw_markdown),
            "error": result.error_message,
        }
        if result.extracted_content:
            entry["extracted"] = self._parse_extracted(result.extracted_content)
        self._results.append(entry)

    @staticmethod
    def _parse_extracted(text: str) -> Any:
        """Best-effort JSON parsing with fallback repairs."""
        import re

        def _try_parse(s: str) -> Any:
            try:
                return json.loads(s)
            except (json.JSONDecodeError, TypeError):
                return None

        # Direct parse
        result = _try_parse(text)
        if result is not None:
            return result

        # Fix trailing commas
        fixed = re.sub(r",\s*([}\]])", r"\1", text)
        result = _try_parse(fixed)
        if result is not None:
            return result

        # Fix unescaped quotes inside string values
        def _fix_inner_quotes(s: str) -> str:
            out = []
            in_string = False
            escape_next = False
            for i, ch in enumerate(s):
                if escape_next:
                    out.append(ch)
                    escape_next = False
                    continue
                if ch == '\\':
                    out.append(ch)
                    escape_next = True
                    continue
                if ch == '"':
                    if not in_string:
                        in_string = True
                        out.append(ch)
                    else:
                        # Check if this quote ends the string value
                        rest = s[i+1:].lstrip()
                        if rest and rest[0] in (',', '}', ']', ':'):
                            in_string = False
                            out.append(ch)
                        else:
                            # Interior quote — escape it
                            out.append('\\"')
                else:
                    out.append(ch)
            return ''.join(out)

        fixed2 = _fix_inner_quotes(fixed)
        result = _try_parse(fixed2)
        if result is not None:
            return result

        # Try closing truncated arrays/objects
        for attempt in [fixed, fixed2]:
            last_brace = attempt.rfind("}")
            if last_brace > 0:
                trimmed = attempt[:last_brace + 1]
                trimmed += "]" * (trimmed.count("[") - trimmed.count("]"))
                result = _try_parse(trimmed)
                if result is not None:
                    return result

        return text

    def finalize(self) -> None:
        if not self._results or not self.to:
            print(f"[email] Skipping: results={len(self._results)}, to={self.to!r}")
            return

        # Check if there are any actual extracted articles
        has_articles = any(
            r.get("extracted") and isinstance(r["extracted"], (list, dict))
            and (len(r["extracted"]) > 0 if isinstance(r["extracted"], list) else True)
            for r in self._results
        )
        if not has_articles:
            print("[email] Skipping: no extracted articles to send")
            return

        recipients = [email.strip() for email in self.to.split(",") if email.strip()]
        print(f"[email] Sending to {', '.join(recipients)} via email API")
        try:
            html_body = self._render_email()
            for recipient in recipients:
                self._send_via_api(recipient, html_body)
            print(f"[email] Sent successfully to {', '.join(recipients)}")
        except Exception as e:
            print(f"[email] FAILED: {e}")
            raise

    @staticmethod
    def _format_ist_datetime() -> str:
        """Return a human-readable datetime in IST, e.g. '1:40 PM Thursday, 19th March 2026'."""
        now = datetime.now(_IST)
        day = now.day
        suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return now.strftime(f"%-I:%M %p %A, {day}{suffix} %B %Y")

    def _render_email(self) -> str:
        total = len(self._results)
        ok = sum(1 for r in self._results if r["success"])
        ts = self._format_ist_datetime()

        # Collect all extracted items across results
        all_items: List[Dict[str, Any]] = []
        sources_seen: List[str] = []
        for r in self._results:
            ext = r.get("extracted")
            source_url = r.get("url", "")
            if source_url and source_url not in sources_seen:
                sources_seen.append(source_url)
            if isinstance(ext, list):
                all_items.extend(ext)
            elif isinstance(ext, dict):
                all_items.append(ext)

        # Build article cards
        articles_html = ""
        for i, item in enumerate(all_items, 1):
            title = item.get("title", "Untitled")
            source = item.get("source", "")
            category = item.get("category", "")
            summary = item.get("summary", "")
            time_ago = item.get("time_ago", "")

            badge = ""
            if category:
                badge = f'<span style="background:#e8f4fd;color:#1a73e8;padding:2px 8px;border-radius:12px;font-size:11px;margin-left:8px;">{category}</span>'

            meta_parts = []
            if source:
                meta_parts.append(source)
            if time_ago:
                meta_parts.append(time_ago)
            meta = " · ".join(meta_parts)

            articles_html += f"""
            <div style="border-left:3px solid #1a73e8;padding:10px 15px;margin-bottom:12px;background:#fafafa;border-radius:0 6px 6px 0;">
                <div style="font-size:15px;font-weight:600;color:#1a1a1a;margin-bottom:4px;">
                    {i}. {title}{badge}
                </div>
                <div style="font-size:12px;color:#888;margin-bottom:4px;">{meta}</div>
                {"<div style='font-size:13px;color:#555;'>" + summary + "</div>" if summary else ""}
            </div>
            """

        # Sources summary
        sources_html = ""
        if sources_seen:
            links = " · ".join(f"<a href='{u}' style='color:#1a73e8;text-decoration:none;'>{u.split('//')[1].split('/')[0]}</a>" for u in sources_seen)
            sources_html = f"<p style='font-size:12px;color:#888;'>Sources: {links}</p>"

        # AI summary block (only rendered when a summary was generated)
        summary_html = ""
        if self.ai_summary:
            summary_html = f"""
            <div style="background:#f0f7ff;border-left:4px solid #1a73e8;border-radius:0 8px 8px 0;padding:14px 16px;margin-bottom:20px;">
                <div style="font-size:12px;font-weight:700;color:#1a73e8;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">
                    AI Summary
                </div>
                <p style="margin:0;font-size:14px;color:#333;line-height:1.6;">{self.ai_summary}</p>
            </div>
            """

        return f"""
        <html><body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; color:#333; max-width:600px; margin:0 auto; padding:20px;">
        <div style="border-bottom:2px solid #1a73e8;padding-bottom:12px;margin-bottom:20px;">
            <h2 style="margin:0;color:#1a1a1a;">📰 IntelliFetch News Feed</h2>
            <p style="color:#888;font-size:13px;margin:6px 0 0 0;">
                {ts} · {len(all_items)} articles from {len(sources_seen)} source{'s' if len(sources_seen) != 1 else ''}
            </p>
        </div>
        {summary_html}
        {articles_html}
        <div style="border-top:1px solid #eee;padding-top:12px;margin-top:20px;">
            {sources_html}
            <p style="font-size:11px;color:#aaa;">Generated by IntelliFetch &nbsp;·&nbsp; Powered by Impeerical — Enterprise AI Automation</p>
        </div>
        </body></html>
        """

    def _send_via_api(self, recipient: str, html_body: str) -> None:
        """Send email via the HTTP API endpoint."""
        payload = {
            "to": recipient,
            "subject": self.subject,
            "html": html_body,
            "text": f"Crawl4AI Results - {self.subject}",
        }

        req = urllib.request.Request(
            EMAIL_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status not in (200, 201, 202):
                    raise Exception(f"Email API returned {response.status}")
                print(f"[email] API call succeeded for {recipient} (status={response.status})", flush=True)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise Exception(f"Email API HTTP {e.code}: {body}")
