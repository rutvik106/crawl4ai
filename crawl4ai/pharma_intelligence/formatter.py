"""
Layer 6: Email-Native HTML Table Formatter
"""
from __future__ import annotations
from datetime import date
from html import escape
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit


# Kept Outlook-friendly: only widely-supported inline styles, table layout, no
# border-radius / box-shadow (Outlook ignores those and they can break a clean
# copy-paste into an email).
TABLE_STYLE = {
    "header_bg": "#0f3d52",
    "row_accent": "#f8fafc",
}

# Daily Bites bifurcates the brief into two sections. Each section uses the same
# 3-column layout (Asset / Molecule | News Summary | Source).
SECTION_STYLES = {
    "key_highlight": {"header_bg": "#0f3d52", "row_accent": "#e8f3f7"},
    "other_news": {"header_bg": "#475569", "row_accent": "#f8fafc"},
}


class PharmaEmailFormatter:
    def format_report(
        self,
        items: List[Dict[str, Any]],
        report_date: Optional[date] = None,
        title: str = "Pharma Daily Intelligence Brief",
    ) -> str:
        if report_date is None:
            report_date = date.today()
        # Daily Bites format: bifurcate into "Key Highlights" and "Other News
        # Highlights", each rendered with the same 3-column table.
        by_score = lambda x: x.get("relevance_score", 0)  # noqa: E731
        highlights = sorted(
            [i for i in items if i.get("is_key_highlight")], key=by_score, reverse=True
        )
        other = sorted(
            [i for i in items if not i.get("is_key_highlight")], key=by_score, reverse=True
        )
        html_parts = [self._render_header(title, report_date)]
        if highlights:
            html_parts.append(
                self._render_section("Key Highlights", highlights, "key_highlight")
            )
        if other:
            html_parts.append(
                self._render_section("Other News Highlights", other, "other_news")
            )
        html_parts.append(self._render_footer())
        return "\n".join(html_parts)

    def format_json_summary(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        highlights = sorted(
            [i for i in items if i.get("is_key_highlight")],
            key=lambda x: x.get("relevance_score", 0), reverse=True
        )
        other = sorted(
            [i for i in items if not i.get("is_key_highlight")],
            key=lambda x: x.get("relevance_score", 0), reverse=True
        )
        return {
            "total_articles_processed": len(items),
            "key_highlights_count": len(highlights),
            "other_news_count": len(other),
            "key_highlights": [self._item_to_dict(i) for i in highlights],
            "other_news": [self._item_to_dict(i) for i in other],
        }

    @classmethod
    def _item_to_dict(cls, item: Dict[str, Any]) -> Dict[str, Any]:
        entities = item.get("entities", {})
        # Column-1 label: 'molecule (Brand)' for drugs, 'M&A - A & B' for deals.
        particular = cls._asset_label(item, entities)
        return {
            "title": item.get("title", ""),
            "headline": item.get("headline", item.get("title", "")),
            "particular": particular,
            "asset_label": particular,
            "molecule": entities.get("molecule"),
            "brand_name": entities.get("brand_name"),
            "counterparties": item.get("counterparties") or entities.get("counterparties", []),
            "transaction_type": entities.get("transaction_type"),
            "company": entities.get("company"),
            "indication": entities.get("indication"),
            "geography": entities.get("geography"),
            "categories": item.get("categories", []),
            "primary_category": item.get("primary_category", ""),
            "therapy_area": item.get("therapy_area"),
            "summary": item.get("summary", ""),
            "key_points": item.get("key_points", []),
            "event_update": item.get("event_update"),
            "evidence": item.get("evidence"),
            "regulatory_status": item.get("regulatory_status"),
            "clinical_stage": item.get("clinical_stage"),
            "strategic_significance": item.get("strategic_significance"),
            "commercial_implications": item.get("commercial_implications"),
            "key_metric": item.get("key_metric"),
            "relevance_score": item.get("relevance_score", 0),
            "score_rationale": item.get("score_rationale", ""),
            "classification_confidence": item.get("classification_confidence", 0.0),
            "is_key_highlight": item.get("is_key_highlight", False),
            "demoted": item.get("demoted", False),
            "demotion_reason": item.get("demotion_reason", ""),
            "previously_covered_on": item.get("previously_covered_on", ""),
            # Resolve the link at persist time so the stored report always keeps a
            # usable source URL for the "Read the full article" cell.
            "url": cls._pick_article_url(item) or item.get("url", ""),
            "source": item.get("source", ""),
            "sources": item.get("sources", []),
            "is_consolidated": item.get("is_consolidated", False),
            "published_at": item.get("published_at", ""),
        }

    @staticmethod
    def _render_header(title: str, report_date: date) -> str:
        safe_title = escape(title)
        return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{safe_title}</title>
</head>
<body style="margin:0;padding:0;background:#f0f4f5;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f5;padding:24px 0;">
<tr><td align="center">
<table width="680" cellpadding="0" cellspacing="0" style="background:#ffffff;">
<tr><td style="background:#0f3d52;padding:24px 32px;">
  <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;">{safe_title}</h1>
  <p style="margin:4px 0 0;color:#a8d4e0;font-size:13px;">{report_date.strftime('%B %d, %Y')}</p>
</td></tr>
"""

    @staticmethod
    def _render_footer() -> str:
        return """\
<tr><td style="background:#f8fafc;padding:20px 32px;border-top:1px solid #e2e8f0;">
  <p style="margin:0;font-size:11px;color:#94a3b8;text-align:center;">
    Generated by IntelliFetch Pharma Intelligence Engine &nbsp;|&nbsp; Powered by Impeerical
  </p>
</td></tr>
</table></td></tr></table>
</body></html>
"""

    def _render_section(self, section_title: str, items: List[Dict], style_key: str) -> str:
        style = SECTION_STYLES[style_key]
        rows = "".join(self._render_row(item, style) for item in items)
        # 3-column layout per the client's specimen:
        #   Asset / Molecule | News Summary | Source
        return f"""\
<tr><td style="padding:22px 32px 8px;">
  <h2 style="margin:0;font-size:15px;font-weight:700;color:{style['header_bg']};
             text-transform:uppercase;letter-spacing:0.5px;
             border-bottom:2px solid {style['header_bg']};padding-bottom:8px;">
    {escape(section_title)}
  </h2>
</td></tr>
<tr><td style="padding:10px 32px 20px;">
<table width="100%" cellpadding="0" cellspacing="0">
<thead><tr style="background:{style['header_bg']};">
  <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:700;color:#ffffff;width:24%;">Asset / Molecule</th>
  <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:700;color:#ffffff;width:58%;">News Summary</th>
  <th style="padding:10px 12px;text-align:center;font-size:11px;font-weight:700;color:#ffffff;width:18%;">Source</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>
</td></tr>
"""

    @staticmethod
    def _asset_label(item: Dict, entities: Dict) -> str:
        """Column-1 label. For drugs: 'molecule (Brand)'. For transactions:
        'M&A - Company A & Company B', 'Licensing - Company A & Company B', etc."""
        # JSON reports persist flattened entity fields. Read both shapes so an
        # HTML report generated after storage retains exactly the same label.
        molecule = entities.get("molecule") or item.get("molecule")
        brand = entities.get("brand_name") or item.get("brand_name")
        event_type = str(entities.get("event_type") or "").lower()
        categories = [str(c).lower() for c in item.get("categories", [])]
        transaction_type = str(
            entities.get("transaction_type") or item.get("transaction_type") or ""
        ).strip().lower()

        deal_prefix = None
        if transaction_type in {"m&a", "ma", "acquisition", "merger"}:
            deal_prefix = "M&A"
        elif transaction_type == "licensing":
            deal_prefix = "Licensing"
        elif transaction_type == "collaboration":
            deal_prefix = "Collaboration"
        elif transaction_type == "partnership":
            deal_prefix = "Partnership"
        elif event_type == "ma" or "m&a activity" in categories:
            deal_prefix = "M&A"
        elif event_type == "licensing" or "licensing deal" in categories:
            deal_prefix = "Licensing"
        elif "collaborat" in event_type or any(
            "collaborat" in c or "partnership" in c for c in categories
        ):
            deal_prefix = "Collaboration"

        # Deal-type items without a specific molecule → name the counterparties.
        if deal_prefix and not molecule:
            parties = [
                str(p).strip()
                for p in (item.get("counterparties") or entities.get("counterparties") or [])
                if str(p).strip()
            ]
            if not parties and (entities.get("company") or item.get("company")):
                parties = [str(entities.get("company") or item.get("company")).strip()]
            if parties:
                return f"{deal_prefix} - {' & '.join(parties[:3])}"

        # Drug items → 'molecule (Brand)' when both are available.
        if molecule and brand and str(brand).lower() != str(molecule).lower():
            return f"{molecule} ({brand})"
        if molecule:
            return str(molecule)
        if brand:
            return str(brand)
        persisted_label = item.get("asset_label") or item.get("particular")
        if persisted_label:
            return str(persisted_label)
        headline = item.get("headline") or item.get("title") or "—"
        return str(headline)[:90]

    @staticmethod
    def _safe_article_url(value: Any) -> str:
        """Allow only clickable web URLs in the source column."""
        url = str(value or "").strip()
        try:
            parsed = urlsplit(url)
        except ValueError:
            return ""
        return url if parsed.scheme in {"http", "https"} and parsed.netloc else ""

    @classmethod
    def _pick_article_url(cls, item: Dict) -> str:
        """Resolve the article URL from any of the shapes an item may carry.

        The Source column must always render the "Read the full article" link, so
        a payload that stored the link under an alternate key (or nested under
        ``entities``) must not silently produce an empty cell.
        """
        candidates = [
            item.get("url"), item.get("link"), item.get("source_url"),
            item.get("article_url"), item.get("href"),
        ]
        entities = item.get("entities") or {}
        if isinstance(entities, dict):
            candidates += [entities.get("url"), entities.get("link")]
        for candidate in candidates:
            safe = cls._safe_article_url(candidate)
            if safe:
                return safe
        return ""

    def _render_row(self, item: Dict, style: Dict) -> str:
        entities = item.get("entities", {})
        asset_label = self._asset_label(item, entities)
        # The description is the primary content; everything extra (status/stage/
        # metric/source sub-lines) has been removed so the summary stands alone.
        summary = item.get("summary") or item.get("headline") or item.get("title") or ""
        url = self._pick_article_url(item)

        link_cell = (
            f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer" style="display:inline-block;'
            f'background:#0f3d52;color:#ffffff;font-size:11px;font-weight:600;'
            f'padding:6px 12px;text-decoration:none;">Read the full article</a>'
            if url else "—"
        )

        summary_html = f'<span style="font-size:12px;color:#334155;line-height:1.55;">{escape(str(summary))}</span>'

        # Keep this cell limited to the exact client-requested identifier.
        mol_html = f'<b style="font-size:13px;color:#0f2d3d;">{escape(str(asset_label))}</b>'
        return (
            f'<tr style="border-bottom:1px solid #e2e8f0;">'
            f'<td style="padding:12px;vertical-align:top;background:{style["row_accent"]};">{mol_html}</td>'
            f'<td style="padding:12px;vertical-align:top;">{summary_html}</td>'
            f'<td style="padding:12px;vertical-align:top;text-align:center;">{link_cell}</td>'
            f'</tr>'
        )
