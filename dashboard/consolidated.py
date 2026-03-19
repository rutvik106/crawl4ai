"""Consolidated report generation — weekly/monthly summaries of all job results.

Called by the nightly scheduler check and by the on-demand API endpoint.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dashboard import db


async def generate_and_send_consolidated_report(
    schedule: Dict[str, Any],
    settings: Dict[str, str],
    since: Optional[datetime] = None,
) -> None:
    """Gather all job results for *schedule* since *since*, build an AI consolidated
    report, and email it to the schedule recipients.

    Args:
        schedule: Full schedule row from the DB.
        settings: Key-value settings dict (groq key, SMTP creds, etc.).
        since: Only include jobs created on or after this timestamp.
               Defaults to 7 days ago for weekly, 31 days ago for monthly.
    """
    _log = lambda msg: print(msg, flush=True)

    schedule_id = schedule["id"]
    frequency = schedule.get("consolidated_frequency") or "weekly"

    if since is None:
        lookback_days = 7 if frequency == "weekly" else 31
        since = datetime.now() - timedelta(days=lookback_days)

    jobs = db.get_jobs_for_schedule(schedule_id, since=since)
    _log(f"[consolidated] Schedule {schedule_id}: found {len(jobs)} job(s) since {since.date()}")

    # Collect articles from all jobs
    all_articles: List[Dict[str, Any]] = []
    for job in jobs:
        extracted = job.get("extracted_articles")
        if not extracted:
            continue
        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except Exception:
                continue
        if isinstance(extracted, list):
            all_articles.extend(a for a in extracted if isinstance(a, dict))
        elif isinstance(extracted, dict):
            all_articles.append(extracted)

    if not all_articles:
        _log(f"[consolidated] Schedule {schedule_id}: no articles found, skipping report")
        return

    # Resolve recipients (schedule-level field or from config)
    recipients = schedule.get("recipients", "")
    if not recipients:
        config = schedule.get("config") or {}
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except Exception:
                config = {}
        recipients = config.get("recipients", "")

    if not recipients:
        _log(f"[consolidated] Schedule {schedule_id}: no recipients configured, skipping")
        return

    groq_key = settings.get("groq_api_key", os.getenv("GROQ_API_KEY", ""))
    llm_provider = settings.get("llm_provider", "groq/llama-3.1-8b-instant")

    if not groq_key:
        _log("[consolidated] No Groq API key configured, cannot generate report")
        return

    # Build article lines for the LLM (cap at 100 to stay within token limits)
    article_lines: List[str] = []
    for i, art in enumerate(all_articles[:100], 1):
        parts: List[str] = [f"{i}."]
        title = art.get("title", "").strip()
        source = art.get("source", "").strip()
        category = art.get("category", "").strip()
        summary = art.get("summary", "").strip()
        if title:
            parts.append(title)
        if source:
            parts.append(f"[{source}]")
        if category:
            parts.append(f"({category})")
        if summary:
            parts.append(f"— {summary}")
        article_lines.append(" ".join(parts))

    period_label = "weekly" if frequency == "weekly" else "monthly"
    date_range = f"{since.strftime('%b %d')} – {datetime.now().strftime('%b %d, %Y')}"

    prompt = (
        f"You are a professional analyst. Below are {len(all_articles)} articles/items collected "
        f"from '{schedule.get('url', 'a website')}' over the past {period_label} period "
        f"({date_range}).\n\n"
        f"Create a comprehensive consolidated {period_label} report with these sections:\n"
        f"1. **Executive Summary** (3-4 sentences covering the dominant themes)\n"
        f"2. **Key Trends & Patterns** (3-5 bullet points of recurring themes)\n"
        f"3. **Notable Headlines** (top 5-7 most significant items with brief context)\n"
        f"4. **Overall Assessment** (1-2 closing sentences about the period)\n\n"
        f"Articles collected:\n" + "\n".join(article_lines)
    )

    try:
        import litellm
        response = await litellm.acompletion(
            model=llm_provider,
            api_key=groq_key,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional analyst. Write clear, well-structured "
                        "consolidated reports from news and data collections. "
                        "Use the exact section headers requested."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        report_text = response.choices[0].message.content.strip()
        _log(f"[consolidated] Schedule {schedule_id}: report generated ({len(report_text)} chars)")
    except Exception as e:
        _log(f"[consolidated] Schedule {schedule_id}: LLM call failed: {e}")
        return

    # Build and send the email
    subject = (
        f"Consolidated {period_label.capitalize()} Report – "
        f"{schedule.get('job_name', 'Crawl4AI')} ({date_range})"
    )
    html_body = _render_consolidated_email(
        report_text=report_text,
        schedule_name=schedule.get("job_name", "Crawl4AI"),
        url=schedule.get("url", ""),
        article_count=len(all_articles),
        job_count=len(jobs),
        date_range=date_range,
        period_label=period_label,
    )

    from crawl4ai.output.email_output import EmailOutput
    mailer = EmailOutput(
        to=recipients,
        subject=subject,
    )
    recipient_list = [e.strip() for e in recipients.split(",") if e.strip()]
    for recipient in recipient_list:
        mailer._send_via_api(recipient, html_body)
    _log(f"[consolidated] Report sent to {recipients} ({len(all_articles)} articles, {len(jobs)} runs)")

    # Record the send time so we don't double-send
    db.update_schedule(schedule_id, consolidated_last_sent=datetime.now().isoformat())


def _render_consolidated_email(
    report_text: str,
    schedule_name: str,
    url: str,
    article_count: int,
    job_count: int,
    date_range: str,
    period_label: str,
) -> str:
    """Convert the LLM report text to a styled HTML email."""

    # Convert **bold** markers to <strong>
    html_content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", report_text)

    # Convert numbered section headers (e.g. "1. <strong>Title</strong>") to <h4>
    html_content = re.sub(
        r"^\d+\.\s+<strong>(.+?)</strong>",
        r'<h4 style="margin:20px 0 6px 0;color:#0f2d3d;font-size:14px;border-bottom:1px solid #e2e8f0;padding-bottom:4px;">\1</h4>',
        html_content,
        flags=re.MULTILINE,
    )

    # Convert bullet points to <li>
    html_content = re.sub(r"^[-•*]\s+(.+)$", r"<li>\1</li>", html_content, flags=re.MULTILINE)

    # Wrap consecutive <li> blocks into <ul>
    html_content = re.sub(
        r"(<li>.*?</li>\n?)+",
        lambda m: f'<ul style="margin:6px 0 10px 0;padding-left:20px;color:#555;font-size:13px;line-height:1.7;">{m.group()}</ul>',
        html_content,
        flags=re.DOTALL,
    )

    # Wrap remaining plain paragraphs
    parts = []
    for block in html_content.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("<h4") or block.startswith("<ul"):
            parts.append(block)
        else:
            parts.append(
                f'<p style="margin:8px 0;font-size:13px;color:#444;line-height:1.7;">{block}</p>'
            )
    body_html = "\n".join(parts)

    domain = url.split("//")[1].split("/")[0] if "//" in url else url

    return f"""
    <html>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
                 color:#333;max-width:640px;margin:0 auto;padding:24px;">

      <!-- Header -->
      <div style="border-bottom:3px solid #0f3d52;padding-bottom:16px;margin-bottom:22px;">
        <h2 style="margin:0 0 6px 0;color:#0f2d3d;font-size:20px;">
          📊 Consolidated {period_label.capitalize()} Report
        </h2>
        <p style="margin:0;color:#64748b;font-size:13px;">
          <strong>{schedule_name}</strong>
          &nbsp;·&nbsp;
          <a href="{url}" style="color:#1a73e8;text-decoration:none;">{domain}</a>
        </p>
      </div>

      <!-- Stats bar -->
      <div style="display:flex;gap:0;background:#f0f7ff;border-radius:10px;
                  border:1px solid #dde6e9;overflow:hidden;margin-bottom:22px;">
        <div style="flex:1;text-align:center;padding:14px 10px;">
          <div style="font-size:24px;font-weight:700;color:#0f3d52;">{article_count}</div>
          <div style="font-size:11px;color:#64748b;margin-top:2px;text-transform:uppercase;letter-spacing:0.05em;">Articles</div>
        </div>
        <div style="width:1px;background:#dde6e9;"></div>
        <div style="flex:1;text-align:center;padding:14px 10px;">
          <div style="font-size:24px;font-weight:700;color:#0f3d52;">{job_count}</div>
          <div style="font-size:11px;color:#64748b;margin-top:2px;text-transform:uppercase;letter-spacing:0.05em;">Crawl Runs</div>
        </div>
        <div style="width:1px;background:#dde6e9;"></div>
        <div style="flex:1;text-align:center;padding:14px 10px;">
          <div style="font-size:13px;font-weight:600;color:#0f3d52;">{date_range}</div>
          <div style="font-size:11px;color:#64748b;margin-top:2px;text-transform:uppercase;letter-spacing:0.05em;">Period</div>
        </div>
      </div>

      <!-- Report content -->
      <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;
                  padding:20px 22px;margin-bottom:22px;">
        {body_html}
      </div>

      <!-- Footer -->
      <p style="font-size:11px;color:#aaa;margin:0;text-align:center;">
        Generated by IntelliFetch · Powered by Impeerical — Enterprise AI Automation · Consolidated {period_label} report · {date_range}
      </p>

    </body>
    </html>
    """
