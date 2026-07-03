"""
Layer 6: Email-Native HTML Table Formatter
"""
from __future__ import annotations
from datetime import date
from typing import Any, Dict, List, Optional


SECTION_STYLES = {
    "key_highlight": {
        "header_bg": "#0f3d52",
        "row_accent": "#e8f3f7",
        "badge_bg": "#6dc135",
        "badge_text": "#ffffff",
    },
    "other_news": {
        "header_bg": "#475569",
        "row_accent": "#f8fafc",
        "badge_bg": "#e2e8f0",
        "badge_text": "#475569",
    },
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
        highlights = sorted(
            [i for i in items if i.get("is_key_highlight")],
            key=lambda x: x.get("relevance_score", 0), reverse=True
        )
        other = sorted(
            [i for i in items if not i.get("is_key_highlight")],
            key=lambda x: x.get("relevance_score", 0), reverse=True
        )
        html_parts = [self._render_header(title, report_date)]
        if highlights:
            html_parts.append(self._render_section("Key Highlights", highlights, "key_highlight"))
        if other:
            html_parts.append(self._render_section("Other News", other, "other_news"))
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

    @staticmethod
    def _item_to_dict(item: Dict[str, Any]) -> Dict[str, Any]:
        entities = item.get("entities", {})
        particular = (
            entities.get("molecule") or entities.get("brand_name")
            or item.get("headline") or item.get("title", "")
        )
        return {
            "title": item.get("title", ""),
            "headline": item.get("headline", item.get("title", "")),
            "particular": particular,
            "molecule": entities.get("molecule"),
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
            "url": item.get("url", ""),
            "source": item.get("source", ""),
            "sources": item.get("sources", []),
            "is_consolidated": item.get("is_consolidated", False),
            "published_at": item.get("published_at", ""),
        }

    @staticmethod
    def _render_header(title: str, report_date: date) -> str:
        return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f0f4f5;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f5;padding:24px 0;">
<tr><td align="center">
<table width="680" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
<tr><td style="background:#0f3d52;padding:28px 32px;">
  <table width="100%"><tr>
    <td><h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;">{title}</h1>
        <p style="margin:4px 0 0;color:#a8d4e0;font-size:13px;">{report_date.strftime('%B %d, %Y')}</p></td>
    <td align="right"><span style="background:#6dc135;color:#fff;font-size:11px;font-weight:700;
        padding:4px 10px;border-radius:12px;">DAILY BRIEF</span></td>
  </tr></table>
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
        highlights_label = "Highlights (Key)" if style_key == "key_highlight" else "Highlights (Other)"
        # 3-column layout matching the client's "Daily Bites" specimen:
        #   Molecule/Particular | Highlights (Key) | View Article
        return f"""\
<tr><td style="padding:24px 32px 8px;">
  <h2 style="margin:0 0 12px;font-size:15px;font-weight:700;color:{style['header_bg']};
             text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {style['header_bg']};
             padding-bottom:8px;">
    {section_title}
    <span style="font-size:11px;font-weight:400;background:{style['header_bg']};color:#fff;
                 padding:2px 8px;border-radius:10px;margin-left:8px;">{len(items)}</span>
  </h2>
</td></tr>
<tr><td style="padding:0 32px 16px;">
<table width="100%" cellpadding="0" cellspacing="0">
<thead><tr style="background:{style['header_bg']};">
  <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:700;color:#ffffff;width:26%;">Molecule/Particular</th>
  <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:700;color:#ffffff;width:58%;">{highlights_label}</th>
  <th style="padding:10px 12px;text-align:center;font-size:11px;font-weight:700;color:#ffffff;width:16%;">View Article</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>
</td></tr>
"""

    @staticmethod
    def _particular(item: Dict, entities: Dict) -> str:
        """Column-1 label: the molecule/brand when available, else a concise
        'particular' describing the deal/event (matches specimen rows such as
        'M&A - Zydus and Assertio')."""
        molecule = entities.get("molecule") or entities.get("brand_name")
        if molecule:
            return str(molecule)
        # Non-molecule items (M&A, licensing, corporate) — fall back to the
        # headline which the summarizer phrases as a short particular.
        headline = item.get("headline") or item.get("title") or "—"
        return str(headline)[:90]

    def _render_row(self, item: Dict, style: Dict) -> str:
        entities = item.get("entities", {})
        particular = self._particular(item, entities)
        company = entities.get("company") or ""
        therapy = item.get("therapy_area") or ""
        summary = item.get("summary") or item.get("headline") or item.get("title") or ""
        key_metric = item.get("key_metric")
        regulatory_status = item.get("regulatory_status")
        clinical_stage = item.get("clinical_stage")
        url = item.get("url", "#")
        sources = item.get("sources") or ([item.get("source")] if item.get("source") else [])
        source_text = " + ".join(s for s in sources if s)[:60] if sources else ""

        link_cell = (
            f'<a href="{url}" target="_blank" style="display:inline-block;'
            f'background:#0f3d52;color:#ffffff;font-size:11px;font-weight:600;'
            f'padding:6px 12px;border-radius:6px;text-decoration:none;">Read the full article</a>'
            if url and url != "#" else "—"
        )

        # Daily Bites uses compact prose. Structured fields remain available in
        # JSON, while the email surfaces status/stage without duplicative bullets.
        highlights = f'<span style="font-size:12px;color:#334155;line-height:1.55;">{summary[:900]}</span>'
        detail_bits = [str(v).rstrip(".") for v in (regulatory_status, clinical_stage) if v]
        if detail_bits:
            highlights += (
                f'<br/><span style="font-size:10px;color:#64748b;">'
                f'{" &nbsp;|&nbsp; ".join(detail_bits)}</span>'
            )
        if key_metric:
            highlights += f'<br/><b style="font-size:11px;color:#0f3d52;">{key_metric}</b>'
        if source_text:
            highlights += (
                f'<br/><span style="font-size:10px;color:#94a3b8;">Source: {source_text}</span>'
            )

        mol_html = (
            f'<b style="font-size:13px;color:#0f2d3d;">{particular}</b>'
            + (f'<br/><span style="font-size:10px;color:#64748b;">{company}</span>' if company else '')
            + (f'<br/><span style="font-size:10px;color:#94a3b8;">{therapy}</span>' if therapy else '')
        )
        return (
            f'<tr style="border-bottom:1px solid #e2e8f0;">'
            f'<td style="padding:12px;vertical-align:top;background:{style["row_accent"]};">{mol_html}</td>'
            f'<td style="padding:12px;vertical-align:top;">{highlights}</td>'
            f'<td style="padding:12px;vertical-align:top;text-align:center;">{link_cell}</td>'
            f'</tr>'
        )
