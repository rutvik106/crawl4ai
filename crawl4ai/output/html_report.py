"""HTML report output backend — generates a styled, browser-viewable report."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import OutputBackend
from ..models import CrawlResult


class HTMLReportOutput(OutputBackend):
    """Generates a self-contained HTML report of crawl results.

    Args:
        path: Output HTML file path. Defaults to ``crawl_report.html``.
        title: Report title shown in the header.
        open_browser: If True, auto-opens the report in the default browser.
    """

    def __init__(
        self,
        path: str = "crawl_report.html",
        title: str = "Crawl4AI Report",
        open_browser: bool = False,
    ) -> None:
        self.path = path
        self.title = title
        self.open_browser = open_browser
        self._results: List[Dict[str, Any]] = []

    def save(self, result: CrawlResult, metadata: Optional[Dict[str, Any]] = None) -> None:
        entry: Dict[str, Any] = {
            "url": result.url,
            "success": result.success,
            "status_code": result.status_code,
            "markdown_length": len(result.markdown.raw_markdown),
            "markdown_preview": result.markdown.raw_markdown[:500],
            "error": result.error_message,
        }
        if result.extracted_content:
            try:
                entry["extracted"] = json.loads(result.extracted_content)
            except (json.JSONDecodeError, TypeError):
                entry["extracted"] = result.extracted_content
        if metadata:
            entry["metadata"] = metadata
        self._results.append(entry)

    def finalize(self) -> None:
        html = self._render()
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(html)

        if self.open_browser:
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(self.path)}")

    def _render(self) -> str:
        total = len(self._results)
        ok = sum(1 for r in self._results if r["success"])
        fail = total - ok
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        rows = ""
        for i, r in enumerate(self._results, 1):
            status = '<span class="badge ok">OK</span>' if r["success"] else '<span class="badge fail">FAIL</span>'
            extracted_html = ""
            if r.get("extracted"):
                ext = r["extracted"]
                if isinstance(ext, list):
                    extracted_html = f"<strong>{len(ext)} items extracted</strong>"
                    items = "".join(
                        f"<li>{_esc(json.dumps(item, ensure_ascii=False)[:200])}</li>"
                        for item in ext[:5]
                    )
                    extracted_html += f"<ul>{items}</ul>"
                    if len(ext) > 5:
                        extracted_html += f"<p class='muted'>...and {len(ext) - 5} more</p>"
                else:
                    extracted_html = f"<pre>{_esc(str(ext)[:300])}</pre>"

            error_html = f'<p class="error">{_esc(r["error"])}</p>' if r.get("error") else ""

            rows += f"""
            <div class="card">
                <div class="card-header">
                    <span class="num">#{i}</span>
                    {status}
                    <a href="{_esc(r['url'])}" target="_blank">{_esc(r['url'])}</a>
                    <span class="muted">{r['markdown_length']} chars</span>
                </div>
                {error_html}
                <div class="extracted">{extracted_html}</div>
                <details>
                    <summary>Markdown preview</summary>
                    <pre class="md-preview">{_esc(r['markdown_preview'])}</pre>
                </details>
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(self.title)}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #0f172a; color: #e2e8f0; padding: 2rem; line-height: 1.6; }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; color: #38bdf8; }}
    .meta {{ color: #94a3b8; margin-bottom: 1.5rem; font-size: 0.9rem; }}
    .stats {{ display: flex; gap: 1.5rem; margin-bottom: 2rem; }}
    .stat {{ background: #1e293b; padding: 1rem 1.5rem; border-radius: 8px; text-align: center; }}
    .stat .num {{ font-size: 1.8rem; font-weight: 700; color: #38bdf8; display: block; }}
    .stat .label {{ font-size: 0.8rem; color: #94a3b8; text-transform: uppercase; }}
    .card {{ background: #1e293b; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1rem;
             border-left: 3px solid #334155; }}
    .card-header {{ display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }}
    .card-header a {{ color: #38bdf8; text-decoration: none; word-break: break-all; }}
    .card-header a:hover {{ text-decoration: underline; }}
    .badge {{ padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }}
    .badge.ok {{ background: #065f46; color: #6ee7b7; }}
    .badge.fail {{ background: #7f1d1d; color: #fca5a5; }}
    .num {{ color: #64748b; font-weight: 600; }}
    .muted {{ color: #64748b; font-size: 0.85rem; }}
    .error {{ color: #fca5a5; margin-top: 0.5rem; font-size: 0.85rem; }}
    .extracted {{ margin-top: 0.75rem; }}
    .extracted ul {{ padding-left: 1.25rem; font-size: 0.85rem; color: #cbd5e1; }}
    .extracted li {{ margin-bottom: 0.25rem; }}
    details {{ margin-top: 0.75rem; }}
    summary {{ cursor: pointer; color: #94a3b8; font-size: 0.85rem; }}
    summary:hover {{ color: #e2e8f0; }}
    pre {{ background: #0f172a; padding: 0.75rem; border-radius: 6px; font-size: 0.8rem;
           overflow-x: auto; white-space: pre-wrap; color: #94a3b8; margin-top: 0.5rem; }}
</style>
</head>
<body>
<div class="container">
    <h1>{_esc(self.title)}</h1>
    <p class="meta">Generated: {ts}</p>
    <div class="stats">
        <div class="stat"><span class="num">{total}</span><span class="label">Total</span></div>
        <div class="stat"><span class="num">{ok}</span><span class="label">Success</span></div>
        <div class="stat"><span class="num">{fail}</span><span class="label">Failed</span></div>
    </div>
    {rows}
</div>
</body>
</html>"""


def _esc(text: str) -> str:
    """Basic HTML escaping."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
