"""HTML report output backend."""

from __future__ import annotations

import html
import os
from dataclasses import dataclass
from typing import List

from crawl4ai.models import CrawlResult


@dataclass
class _Row:
    url: str
    success: bool
    status_code: int
    error_message: str


class HTMLReportOutput:
    """Collect crawl results and render a summary HTML report at finalize time."""

    def __init__(self, path: str, title: str = "Crawl Report") -> None:
        self.path = path
        self.title = title
        self._rows: List[_Row] = []

    def save(self, result: CrawlResult) -> None:
        self._rows.append(
            _Row(
                url=result.url,
                success=result.success,
                status_code=result.status_code,
                error_message=result.error_message or "",
            )
        )

    def finalize(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        rows_html = "\n".join(
            (
                "<tr>"
                f"<td>{html.escape(row.url)}</td>"
                f"<td>{'✅' if row.success else '❌'}</td>"
                f"<td>{row.status_code}</td>"
                f"<td>{html.escape(row.error_message)}</td>"
                "</tr>"
            )
            for row in self._rows
        )
        doc = f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>{html.escape(self.title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
  </style>
</head>
<body>
  <h1>{html.escape(self.title)}</h1>
  <p>Total results: {len(self._rows)}</p>
  <table>
    <thead>
      <tr><th>URL</th><th>Success</th><th>Status</th><th>Error</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body>
</html>
"""
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(doc)
