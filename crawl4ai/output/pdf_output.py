"""PDF report output backend — generates a beautifully crafted PDF digest.

Uses ``fpdf2`` (pure Python, no system dependencies) for Railway/Vercel
compatibility.

Install:
    pip install fpdf2

Usage::

    from crawl4ai.output.pdf_output import PDFReportOutput

    backend = PDFReportOutput(
        path="output/job123/report.pdf",
        title="Daily Pharma News Digest",
    )
    backend.save(crawl_result)
    backend.finalize()
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .base import OutputBackend
from ..models import CrawlResult

# IST = UTC+5:30
_IST = timezone(timedelta(hours=5, minutes=30))

# Brand colours
_BRAND_PRIMARY = (15, 61, 82)     # #0f3d52 — dark teal
_BRAND_ACCENT = (26, 115, 232)    # #1a73e8 — blue accent
_BRAND_LIGHT = (232, 243, 247)    # #e8f3f7 — light bg
_TEXT_DARK = (15, 45, 61)         # #0f2d3d
_TEXT_MUTED = (100, 116, 139)     # #64748b
_WHITE = (255, 255, 255)
_DIVIDER = (221, 230, 233)        # #dde6e9


class PDFReportOutput(OutputBackend):
    """Generates a branded PDF digest of extracted articles.

    Args:
        path: Output PDF file path.
        title: Report title shown in the header.
        logo_path: Optional path to a JPEG/PNG logo image.
        ai_summary: Optional AI-generated summary to include.
    """

    def __init__(
        self,
        path: str = "report.pdf",
        title: str = "IntelliFetch News Digest",
        logo_path: Optional[str] = None,
        ai_summary: str = "",
    ) -> None:
        self.path = path
        self.title = title
        self.logo_path = logo_path
        self.ai_summary = ai_summary
        self._results: List[Dict[str, Any]] = []

    def save(self, result: CrawlResult, metadata: Optional[Dict[str, Any]] = None) -> None:
        entry: Dict[str, Any] = {
            "url": result.url,
            "success": result.success,
        }
        if result.extracted_content:
            try:
                entry["extracted"] = json.loads(result.extracted_content)
            except (json.JSONDecodeError, TypeError):
                entry["extracted"] = result.extracted_content
        self._results.append(entry)

    def finalize(self) -> None:
        """Render and write the PDF file."""
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        pdf = self._render()
        pdf.output(self.path)
        print(f"[pdf] Report saved: {self.path} ({os.path.getsize(self.path)} bytes)")

    # ------------------------------------------------------------------ #
    # Internal rendering
    # ------------------------------------------------------------------ #

    def _render(self):
        from fpdf import FPDF

        # Collect all extracted articles
        all_items: List[Dict[str, Any]] = []
        sources_seen: List[str] = []
        for r in self._results:
            src = r.get("url", "")
            if src and src not in sources_seen:
                sources_seen.append(src)
            ext = r.get("extracted")
            if isinstance(ext, list):
                all_items.extend(ext)
            elif isinstance(ext, dict):
                all_items.append(ext)

        now_ist = datetime.now(_IST)
        ts = now_ist.strftime("%I:%M %p, %d %B %Y")

        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        # ── Header bar ──────────────────────────────────────────────────
        pdf.set_fill_color(*_BRAND_PRIMARY)
        pdf.rect(0, 0, 210, 36, "F")

        # Logo (if available)
        logo = self.logo_path
        if not logo:
            # Try project-level logo
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            candidate = os.path.join(project_root, "New-Logo-Impeerical.jpg")
            if os.path.exists(candidate):
                logo = candidate

        if logo and os.path.exists(logo):
            try:
                pdf.image(logo, x=10, y=5, h=14)
            except Exception:
                pass

        # Title text
        pdf.set_xy(10, 20)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 8, _safe(self.title), ln=True)

        # Sub-header with date and stats
        pdf.set_xy(10, 38)
        pdf.set_text_color(*_TEXT_MUTED)
        pdf.set_font("Helvetica", "", 9)
        src_label = f"{len(sources_seen)} source{'s' if len(sources_seen) != 1 else ''}"
        pdf.cell(0, 5, f"{ts}  |  {len(all_items)} articles from {src_label}", ln=True)

        pdf.ln(4)

        # ── AI Summary ──────────────────────────────────────────────────
        if self.ai_summary:
            self._draw_ai_summary(pdf)

        # ── Stats row ───────────────────────────────────────────────────
        self._draw_stats_row(pdf, len(all_items), len(sources_seen))

        # ── Articles ────────────────────────────────────────────────────
        if all_items:
            for i, item in enumerate(all_items, 1):
                self._draw_article_card(pdf, i, item)
        else:
            pdf.ln(10)
            pdf.set_text_color(*_TEXT_MUTED)
            pdf.set_font("Helvetica", "I", 11)
            pdf.cell(0, 10, "No articles extracted for this job.", ln=True, align="C")

        # ── Sources ─────────────────────────────────────────────────────
        if sources_seen:
            self._draw_sources(pdf, sources_seen)

        # ── Footer ──────────────────────────────────────────────────────
        self._draw_footer(pdf)

        return pdf

    def _draw_ai_summary(self, pdf) -> None:
        x = pdf.get_x()
        y = pdf.get_y()
        w = 190

        # Light blue background box
        pdf.set_fill_color(240, 247, 255)
        pdf.set_draw_color(*_BRAND_ACCENT)

        # Calculate height needed
        pdf.set_font("Helvetica", "", 9)
        lines = pdf.multi_cell(w - 20, 5, _safe(self.ai_summary), dry_run=True, output="LINES")
        box_h = max(len(lines) * 5 + 18, 25)

        if y + box_h > 277:
            pdf.add_page()
            y = pdf.get_y()

        pdf.rect(10, y, w, box_h, "DF")
        # Left accent bar
        pdf.set_fill_color(*_BRAND_ACCENT)
        pdf.rect(10, y, 3, box_h, "F")

        # Label
        pdf.set_xy(18, y + 4)
        pdf.set_text_color(*_BRAND_ACCENT)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(0, 4, "AI SUMMARY", ln=True)

        # Body
        pdf.set_xy(18, y + 10)
        pdf.set_text_color(*_TEXT_DARK)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(w - 20, 5, _safe(self.ai_summary))

        pdf.set_y(y + box_h + 4)

    def _draw_stats_row(self, pdf, article_count: int, source_count: int) -> None:
        y = pdf.get_y()
        if y + 20 > 277:
            pdf.add_page()
            y = pdf.get_y()

        box_w = 60
        gap = 5
        start_x = (210 - (box_w * 3 + gap * 2)) / 2

        stats = [
            (str(article_count), "Articles"),
            (str(source_count), "Sources"),
            (datetime.now(_IST).strftime("%d %b"), "Report Date"),
        ]

        for i, (value, label) in enumerate(stats):
            x = start_x + i * (box_w + gap)

            # Card background
            pdf.set_fill_color(*_BRAND_LIGHT)
            pdf.set_draw_color(*_DIVIDER)
            pdf.rect(x, y, box_w, 18, "DF")

            # Value
            pdf.set_xy(x, y + 2)
            pdf.set_text_color(*_BRAND_PRIMARY)
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(box_w, 8, value, align="C")

            # Label
            pdf.set_xy(x, y + 10)
            pdf.set_text_color(*_TEXT_MUTED)
            pdf.set_font("Helvetica", "", 7)
            pdf.cell(box_w, 6, label.upper(), align="C")

        pdf.set_y(y + 24)

    def _draw_article_card(self, pdf, index: int, item: Dict[str, Any]) -> None:
        title = _safe(str(item.get("title", "Untitled")))
        source = _safe(str(item.get("source", "")))
        category = _safe(str(item.get("category", "")))
        summary = _safe(str(item.get("summary", "")))
        time_ago = _safe(str(item.get("time_ago", "")))

        y = pdf.get_y()
        x_start = 10
        card_w = 190

        # Estimate height
        pdf.set_font("Helvetica", "B", 10)
        title_lines = pdf.multi_cell(card_w - 20, 5, title, dry_run=True, output="LINES")
        title_h = len(title_lines) * 5

        pdf.set_font("Helvetica", "", 8)
        summary_h = 0
        if summary:
            summary_lines = pdf.multi_cell(card_w - 20, 4, summary, dry_run=True, output="LINES")
            summary_h = len(summary_lines) * 4

        card_h = title_h + summary_h + 16  # padding + meta line
        if summary:
            card_h += 2

        # Page break if needed
        if y + card_h + 4 > 277:
            pdf.add_page()
            y = pdf.get_y()

        # Card background
        pdf.set_fill_color(250, 251, 252)
        pdf.set_draw_color(*_DIVIDER)
        pdf.rect(x_start, y, card_w, card_h, "DF")

        # Left accent stripe
        pdf.set_fill_color(*_BRAND_ACCENT)
        pdf.rect(x_start, y, 2.5, card_h, "F")

        # Index number
        pdf.set_xy(x_start + 6, y + 3)
        pdf.set_text_color(*_BRAND_ACCENT)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(8, 5, f"{index}.")

        # Title
        pdf.set_xy(x_start + 14, y + 3)
        pdf.set_text_color(*_TEXT_DARK)
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(card_w - 22, 5, title)

        # Meta line (source + category + time_ago)
        meta_y = y + 3 + title_h + 2
        pdf.set_xy(x_start + 14, meta_y)
        pdf.set_font("Helvetica", "", 7)

        meta_parts = []
        if source:
            meta_parts.append(source)
        if time_ago:
            meta_parts.append(time_ago)
        meta_text = "  |  ".join(meta_parts)

        pdf.set_text_color(*_TEXT_MUTED)
        if meta_text:
            pdf.cell(0, 4, meta_text, ln=False)

        # Category badge
        if category:
            meta_w = pdf.get_string_width(meta_text) + 4 if meta_text else 0
            badge_x = x_start + 14 + meta_w
            badge_w = pdf.get_string_width(category) + 6
            pdf.set_fill_color(232, 244, 253)
            pdf.set_text_color(*_BRAND_ACCENT)
            pdf.set_font("Helvetica", "", 6)
            pdf.set_xy(badge_x, meta_y)
            pdf.cell(badge_w, 4, category, fill=True, align="C")

        # Summary
        if summary:
            summary_y = meta_y + 6
            pdf.set_xy(x_start + 14, summary_y)
            pdf.set_text_color(85, 95, 110)
            pdf.set_font("Helvetica", "", 8)
            pdf.multi_cell(card_w - 22, 4, summary)

        pdf.set_y(y + card_h + 3)

    def _draw_sources(self, pdf, sources: List[str]) -> None:
        y = pdf.get_y() + 4
        if y + 15 > 277:
            pdf.add_page()
            y = pdf.get_y()

        # Divider line
        pdf.set_draw_color(*_DIVIDER)
        pdf.line(10, y, 200, y)

        pdf.set_xy(10, y + 3)
        pdf.set_text_color(*_TEXT_MUTED)
        pdf.set_font("Helvetica", "B", 7)
        pdf.cell(0, 4, "SOURCES", ln=True)

        pdf.set_font("Helvetica", "", 7)
        for src in sources:
            # Extract domain for display
            try:
                domain = src.split("//")[1].split("/")[0]
            except (IndexError, AttributeError):
                domain = src
            pdf.set_text_color(*_BRAND_ACCENT)
            pdf.cell(0, 4, _safe(domain), ln=True)

    def _draw_footer(self, pdf) -> None:
        # Position footer at page bottom
        y = max(pdf.get_y() + 10, 275)
        if y > 285:
            pdf.add_page()
            y = 275

        pdf.set_draw_color(*_DIVIDER)
        pdf.line(10, y, 200, y)

        pdf.set_xy(10, y + 2)
        pdf.set_text_color(*_TEXT_MUTED)
        pdf.set_font("Helvetica", "", 7)
        pdf.cell(
            0, 4,
            "Generated by IntelliFetch  |  Powered by Impeerical - Enterprise AI Automation",
            align="C",
        )


def _safe(text: str) -> str:
    """Sanitise text for fpdf2 — replace characters that cause encoding issues."""
    if not text:
        return ""
    # Replace common unicode characters with ASCII equivalents
    replacements = {
        "\u2014": "-",   # em dash
        "\u2013": "-",   # en dash
        "\u2018": "'",   # left single quote
        "\u2019": "'",   # right single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u2026": "...", # ellipsis
        "\u2022": "*",   # bullet
        "\u00a0": " ",   # non-breaking space
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # fpdf2 uses latin-1 by default; replace remaining unsupported chars
    return text.encode("latin-1", errors="replace").decode("latin-1")
