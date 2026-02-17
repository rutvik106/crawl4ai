"""Email output backend — sends crawl results via SMTP."""

from __future__ import annotations

import json
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from .base import OutputBackend
from ..models import CrawlResult


class EmailOutput(OutputBackend):
    """Sends crawl results as an HTML email via SMTP.

    Results are accumulated and sent as a single email on ``finalize()``.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        smtp_host: SMTP server hostname.
        smtp_port: SMTP server port.
        smtp_user: SMTP auth username.
        smtp_password: SMTP auth password.
        from_addr: Sender email address.
        use_tls: Whether to use STARTTLS.

    Usage::

        output = EmailOutput(
            to="you@email.com",
            subject="Daily News Crawl",
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_user="bot@gmail.com",
            smtp_password="app-password",
        )
    """

    def __init__(
        self,
        to: str = "",
        subject: str = "Crawl4AI Results",
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        from_addr: str = "",
        use_tls: bool = True,
    ) -> None:
        self.to = to
        self.subject = subject
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_addr = from_addr or smtp_user
        self.use_tls = use_tls
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
        # Pattern: find quotes that aren't structural (not after : or , or [ or { or before } ] , :)
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
        print(f"[email] Sending to {', '.join(recipients)} via {self.smtp_host}:{self.smtp_port} (from={self.from_addr})")
        try:
            html_body = self._render_email()
            self._send(html_body)
            print(f"[email] Sent successfully to {', '.join(recipients)}")
        except Exception as e:
            print(f"[email] FAILED: {e}")
            raise

    def _render_email(self) -> str:
        total = len(self._results)
        ok = sum(1 for r in self._results if r["success"])
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

        return f"""
        <html><body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; color:#333; max-width:600px; margin:0 auto; padding:20px;">
        <div style="border-bottom:2px solid #1a73e8;padding-bottom:12px;margin-bottom:20px;">
            <h2 style="margin:0;color:#1a1a1a;">📰 Crawl4AI News Feed</h2>
            <p style="color:#888;font-size:13px;margin:6px 0 0 0;">
                {ts} · {len(all_items)} articles from {len(sources_seen)} source{'s' if len(sources_seen) != 1 else ''}
            </p>
        </div>
        {articles_html}
        <div style="border-top:1px solid #eee;padding-top:12px;margin-top:20px;">
            {sources_html}
            <p style="font-size:11px;color:#aaa;">Generated by Crawl4AI</p>
        </div>
        </body></html>
        """

    def _send(self, html_body: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = self.subject
        msg["From"] = self.from_addr
        msg["To"] = self.to
        msg.attach(MIMEText(html_body, "html"))

        # Split comma-separated recipients into a list
        recipients = [email.strip() for email in self.to.split(",") if email.strip()]

        # Try STARTTLS first, then fall back to SMTP_SSL (port 465)
        try:
            print(f"[email] Trying STARTTLS on {self.smtp_host}:{self.smtp_port}...", flush=True)
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                if self.use_tls:
                    server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_addr, recipients, msg.as_string())
                print("[email] Sent via STARTTLS", flush=True)
                return
        except (OSError, smtplib.SMTPException) as e:
            print(f"[email] STARTTLS failed: {e}", flush=True)

        # Fallback: SMTP_SSL on port 465
        ssl_port = 465
        print(f"[email] Trying SMTP_SSL on {self.smtp_host}:{ssl_port}...", flush=True)
        with smtplib.SMTP_SSL(self.smtp_host, ssl_port, timeout=15) as server:
            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.from_addr, recipients, msg.as_string())
            print("[email] Sent via SMTP_SSL", flush=True)
