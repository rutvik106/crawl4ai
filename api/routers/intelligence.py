"""Pharma Intelligence API router.

Routes (all under /api prefix from main.py):
  GET  /api/intelligence/report       - fetch stored result for a date
  POST /api/intelligence/process      - queue pipeline generation for a date
  GET  /api/intelligence/status       - poll background generation status
  GET  /api/intelligence/config       - read KPI config
  PUT  /api/intelligence/config       - update KPI config
  GET  /api/intelligence/report/html  - HTML email report
  GET  /api/intelligence/report/pdf   - PDF report (for management circulation)

Storage is PostgreSQL (same DATABASE_URL as dashboard/db.py) so results,
run status, and config survive restarts on Railway/Neon. Articles are pulled
from already-crawled jobs (jobs.extracted_articles) for the requested date.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from datetime import date as DateType, datetime, timedelta
from html import escape
from typing import Any, Callable, Dict, List, Optional

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from api.auth import get_current_user
from crawl4ai.pharma_intelligence import (
    HISTORY_LOOKBACK_DAYS,
    IST,
    CoverageHistory,
    PharmaArticle,
    PharmaEmailFormatter,
    PharmaPipeline,
    is_within_last_24h,
)
from crawl4ai.pharma_intelligence.ontology import (
    DEFAULT_DIMENSION_WEIGHTS,
    KEY_HIGHLIGHT_SCORE_THRESHOLD,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pharma-intelligence"])

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/crawl4ai_dashboard",
)

DEFAULT_CONFIG: Dict[str, Any] = {
    "dimension_weights": dict(DEFAULT_DIMENSION_WEIGHTS),
    "key_highlight_score_threshold": KEY_HIGHLIGHT_SCORE_THRESHOLD,
    "min_score_threshold": 10,
    "schedule_enabled": False,
    "schedule_time": "08:30",
    "schedule_recipients": "",
    "schedule_email_subject": "Daily Pharma Intelligence Brief",
}

_COMPLETED_STATUSES = ("completed", "completed_empty")
_tables_ready = False
_active_runs: set[str] = set()
_active_runs_lock = threading.Lock()


# ── PostgreSQL helpers (sync, called via asyncio.to_thread) ──────────────────────

def _connect():
    return psycopg2.connect(DATABASE_URL)


def _ensure_tables() -> None:
    """Idempotently create the pharma tables on first use."""
    global _tables_ready
    if _tables_ready:
        return
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pharma_results (
                    date_key TEXT PRIMARY KEY,
                    result JSONB NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pharma_runs (
                    date_key TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    error TEXT,
                    pdf_url TEXT,
                    email_sent BOOLEAN NOT NULL DEFAULT FALSE,
                    started_at TIMESTAMP WITH TIME ZONE,
                    finished_at TIMESTAMP WITH TIME ZONE,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pharma_config (
                    id INTEGER PRIMARY KEY,
                    config JSONB NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
        conn.commit()
        _tables_ready = True
    finally:
        conn.close()


def _get_result(date_str: str) -> Optional[Dict[str, Any]]:
    _ensure_tables()
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT result FROM pharma_results WHERE date_key = %s", (date_str,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    result = row["result"]
    return result if isinstance(result, dict) else json.loads(result)


def _load_coverage_history(
    date_str: str, lookback_days: int = HISTORY_LOOKBACK_DAYS
) -> CoverageHistory:
    """Load the previously published briefs preceding ``date_str``.

    Used to avoid resurfacing news already covered in the recent past (client
    feedback: Retatrutide was covered on 8 June and reappeared on 23 July).
    """
    # History is an enhancement, never a hard dependency: a storage problem must
    # not abort the brief, so every failure degrades to "no history".
    conn = None
    try:
        _ensure_tables()
        conn = _connect()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT date_key, result FROM pharma_results
                WHERE date_key < %s
                  AND date_key >= to_char(%s::date - %s::int, 'YYYY-MM-DD')
                ORDER BY date_key DESC
                """,
                (date_str, date_str, lookback_days),
            )
            rows = cur.fetchall()
    except Exception as e:
        logger.warning(
            "[intelligence] Could not load coverage history for %s (%s: %s); "
            "proceeding without history",
            date_str, type(e).__name__, e,
        )
        return CoverageHistory()
    finally:
        if conn is not None:
            conn.close()

    reports: List[tuple] = []
    for row in rows:
        result = row.get("result")
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                continue
        if isinstance(result, dict):
            reports.append((row.get("date_key"), result))
    history = CoverageHistory.from_reports(reports)
    logger.info(
        "[intelligence] %s: coverage history loaded from %d prior briefs (%d items)",
        date_str, len(reports), len(history.entries),
    )
    return history


def _store_result(date_str: str, result: Dict[str, Any]) -> None:
    _ensure_tables()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pharma_results (date_key, result, created_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (date_key) DO UPDATE
                    SET result = EXCLUDED.result, created_at = NOW()
                """,
                (date_str, Json(result)),
            )
        conn.commit()
    finally:
        conn.close()


def _set_run_status(
    date_str: str,
    status: str,
    *,
    error: Optional[str] = None,
    pdf_url: Optional[str] = None,
    email_sent: bool = False,
) -> None:
    """Persist run state so polling survives navigation and HTTP timeouts."""
    _ensure_tables()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pharma_runs (
                    date_key, status, error, pdf_url, email_sent,
                    started_at, finished_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    CASE WHEN %s = 'running' THEN NOW() ELSE NULL END,
                    CASE WHEN %s IN ('completed', 'failed') THEN NOW() ELSE NULL END,
                    NOW()
                )
                ON CONFLICT (date_key) DO UPDATE SET
                    status = EXCLUDED.status,
                    error = EXCLUDED.error,
                    pdf_url = EXCLUDED.pdf_url,
                    email_sent = EXCLUDED.email_sent,
                    started_at = CASE
                        WHEN EXCLUDED.status = 'running' THEN NOW()
                        WHEN EXCLUDED.status = 'pending' THEN NULL
                        ELSE pharma_runs.started_at
                    END,
                    finished_at = CASE
                        WHEN EXCLUDED.status IN ('completed', 'failed') THEN NOW()
                        WHEN EXCLUDED.status = 'pending' THEN NULL
                        ELSE pharma_runs.finished_at
                    END,
                    updated_at = NOW()
                """,
                (date_str, status, error, pdf_url, email_sent, status, status),
            )
        conn.commit()
    finally:
        conn.close()


def _get_run_status(date_str: str) -> Dict[str, Any]:
    _ensure_tables()
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM pharma_runs WHERE date_key = %s", (date_str,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return {"date": date_str, "status": "not_started"}
    result = dict(row)
    result["date"] = result.pop("date_key")
    for key in ("started_at", "finished_at", "updated_at"):
        if result.get(key):
            result[key] = result[key].isoformat()
    return result


def _get_config() -> Dict[str, Any]:
    _ensure_tables()
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT config FROM pharma_config WHERE id = 1")
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return dict(DEFAULT_CONFIG)
    cfg = row["config"]
    stored = cfg if isinstance(cfg, dict) else json.loads(cfg)
    # Merge with defaults so new keys are always present, and drop legacy keys
    # (kpi_weights / bundle_configs) that older stored configs may still carry -
    # they predate the contextual-scoring rework and are no longer read anywhere.
    merged = dict(DEFAULT_CONFIG)
    merged.update(stored)
    merged.pop("kpi_weights", None)
    merged.pop("bundle_configs", None)
    return merged


def _store_config(cfg: Dict[str, Any]) -> None:
    _ensure_tables()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pharma_config (id, config, updated_at)
                VALUES (1, %s, NOW())
                ON CONFLICT (id) DO UPDATE
                    SET config = EXCLUDED.config, updated_at = NOW()
                """,
                (Json(cfg),),
            )
        conn.commit()
    finally:
        conn.close()


def _fetch_articles_for_date(date_str: str) -> List[PharmaArticle]:
    """Pull articles published in the 24h window ending on ``date_str``.

    Jobs from ``date_str`` *and the prior day* are scanned so that late-evening
    news crawled the day before is not missed, then each article is filtered to
    the rolling 24h window via its own publication date/time (never-drop applies
    only to relevance, not recency — stale items must not leak into the brief).
    """
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT extracted_articles FROM jobs
                WHERE status IN %s
                  AND created_at::date BETWEEN (%s::date - INTERVAL '1 day') AND %s::date
                ORDER BY created_at ASC
                """,
                (_COMPLETED_STATUSES, date_str, date_str),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    raw: List[Dict[str, Any]] = []
    for row in rows:
        extracted = row.get("extracted_articles")
        if not extracted:
            continue
        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except Exception:
                continue
        if isinstance(extracted, list):
            raw.extend(a for a in extracted if isinstance(a, dict))
        elif isinstance(extracted, dict):
            raw.append(extracted)

    # Reference time for the rolling window: "now" when generating today's brief,
    # otherwise the end of the requested day (for historical re-runs).
    today_str = DateType.today().isoformat()
    if date_str == today_str:
        ref = datetime.now(IST)
    else:
        ref = datetime.fromisoformat(date_str).replace(
            hour=23, minute=59, second=59, tzinfo=IST
        )

    recent = [a for a in raw if is_within_last_24h(a, ref)]
    logger.info(
        "[intelligence] %s: %d crawled articles, %d within last 24h",
        date_str, len(raw), len(recent),
    )
    return [_to_pharma_article(a) for a in recent]


def _to_pharma_article(a: Dict[str, Any]) -> PharmaArticle:
    """Map a stored article dict (title/summary/source/category/...) to PharmaArticle."""
    title = (a.get("title") or "").strip()
    summary = (a.get("summary") or "").strip()
    text = (a.get("content") or a.get("text") or a.get("body") or summary or "").strip()
    url = (
        a.get("url") or a.get("link") or a.get("source_url")
        or a.get("article_url") or a.get("href") or ""
    ).strip()
    source = (a.get("source") or "").strip()
    # Crawled articles carry recency in `published_date` / `time_ago`; older
    # payloads may use `published_at` / `published` / `date`. Capture whichever
    # is present so the published timestamp is never silently lost.
    published = (
        a.get("published_at") or a.get("published_date") or a.get("published")
        or a.get("date") or ""
    ).strip()
    time_ago = (a.get("time_ago") or "").strip()
    category = (a.get("category") or "").strip()
    return PharmaArticle(
        title=title, text=text, summary=summary, url=url,
        source=source, published_at=published, category=category,
        extra={"time_ago": time_ago} if time_ago else {},
    )

# ── LLM client ────────────────────────────────────────────────────────────────
# Provider is selected via PHARMA_LLM_PROVIDER ("openai" | "anthropic").
# This lets us A/B the same articles across models (e.g. GPT vs Claude) without
# changing pipeline code. Falls back to rule-based processing if unavailable.

def _make_llm_client() -> Optional[Callable[[str, str], str]]:
    provider = os.environ.get("PHARMA_LLM_PROVIDER", "openai").strip().lower()
    if provider == "anthropic":
        return _make_anthropic_client()
    return _make_openai_client()


def _make_openai_client() -> Optional[Callable[[str, str], str]]:
    try:
        from dashboard import db
        settings = db.get_all_settings()
    except Exception:
        settings = {}

    groq_key = settings.get("groq_api_key") or os.getenv("GROQ_API_KEY", "")
    llm_provider = settings.get("llm_provider") or "groq/llama-3.1-8b-instant"
    openai_key = os.getenv("OPENAI_API_KEY", "")

    if not (groq_key or openai_key):
        logger.warning("[pharma-llm] No Groq/OpenAI key configured; OpenAI-family client unavailable")
        return None

    try:
        import litellm
    except Exception as e:
        logger.warning("[pharma-llm] litellm unavailable (%s: %s); OpenAI-family client unavailable", type(e).__name__, e)
        return None

    model = llm_provider if groq_key else "gpt-4o-mini"
    api_key = groq_key or openai_key

    def call_llm(system: str, user: str) -> str:
        resp = litellm.completion(
            model=model,
            api_key=api_key,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=2048,
        )
        return resp.choices[0].message.content or ""

    logger.info("[pharma-llm] Using OpenAI-family model '%s'", model)
    return call_llm


def _make_anthropic_client() -> Optional[Callable[[str, str], str]]:
    """Native Anthropic Claude adapter.

    Claude takes the system prompt as a top-level argument (not a message role),
    so we map our (system, user) signature accordingly. Reads ANTHROPIC_API_KEY
    and PHARMA_LLM_MODEL (defaults to a current Claude model).

    NOTE: the previous default ("claude-3-5-sonnet-latest") 404s on current
    Anthropic accounts. Since every pipeline layer silently falls back to
    rule-based processing on an LLM error, a bad model name here used to
    degrade the whole brief (one-line summaries, weak categorization) with
    no visible error anywhere. Keep this default a model that is verified to
    work, and prefer setting PHARMA_LLM_MODEL explicitly per-environment.
    """
    try:
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("[pharma-llm] ANTHROPIC_API_KEY not set; Anthropic client unavailable")
            return None
        model = os.environ.get("PHARMA_LLM_MODEL", "claude-sonnet-4-5-20250929")
        client = anthropic.Anthropic(api_key=api_key)

        def call_llm(system: str, user: str) -> str:
            resp = client.messages.create(
                model=model,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=0.1,
                max_tokens=2048,
            )
            parts = [
                block.text for block in resp.content
                if getattr(block, "type", None) == "text"
            ]
            return "".join(parts)

        logger.info("[pharma-llm] Using Anthropic model '%s'", model)
        return call_llm
    except Exception as e:
        logger.warning("[pharma-llm] Failed to build Anthropic client (%s: %s)", type(e).__name__, e)
        return None


# ── Request models ───────────────────────────────────────────────

class ArticleInput(BaseModel):
    title: str
    text: Optional[str] = None
    summary: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    published_at: Optional[str] = None
    category: Optional[str] = None


class ProcessRequest(BaseModel):
    # Optional: when omitted, articles are pulled from crawled jobs for `date`.
    articles: Optional[List[ArticleInput]] = None
    date: Optional[str] = None  # YYYY-MM-DD, defaults to today


class KPIConfigUpdate(BaseModel):
    dimension_weights: Optional[Dict[str, int]] = None
    key_highlight_score_threshold: Optional[int] = None
    min_score_threshold: Optional[int] = None
    schedule_enabled: Optional[bool] = None
    schedule_time: Optional[str] = None
    schedule_recipients: Optional[str] = None
    schedule_email_subject: Optional[str] = None


def _generate_report(date_str: str, articles: Optional[List[PharmaArticle]] = None) -> Dict[str, Any]:
    """Run the heavy pipeline synchronously inside a worker thread."""
    articles = articles if articles is not None else _fetch_articles_for_date(date_str)
    if not articles:
        raise ValueError(
            f"No crawled articles found for {date_str}. Run the source crawl jobs first."
        )

    pharma_cfg = _get_config()
    pipeline = PharmaPipeline(
        llm_client=_make_llm_client(),
        min_score_threshold=pharma_cfg.get("min_score_threshold", 10),
        run_deduplication=True,
        key_highlight_threshold=pharma_cfg.get(
            "key_highlight_score_threshold", KEY_HIGHLIGHT_SCORE_THRESHOLD
        ),
        dimension_weights=pharma_cfg.get("dimension_weights", DEFAULT_DIMENSION_WEIGHTS),
        history=_load_coverage_history(date_str),
    )
    results = pipeline.process(articles)

    formatter = PharmaEmailFormatter()
    summary = formatter.format_json_summary([r.to_dict() for r in results])
    summary["generated_at"] = date_str
    stats = pipeline.last_run_stats
    summary["demoted_count"] = stats.get(
        "demoted_count", sum(1 for r in results if r.demoted)
    )
    summary["consolidated_count"] = stats.get("consolidated_count", 0)
    summary["excluded_count"] = stats.get("excluded_count", 0)
    summary["previously_covered_count"] = stats.get("previously_covered_count", 0)
    _store_result(date_str, summary)
    return summary


def _upload_report_pdf(date_str: str, pdf_bytes: bytes) -> str:
    """Upload a generated PDF and return its public Vercel Blob URL."""
    from dashboard import db

    settings = db.get_all_settings()
    token = settings.get("blob_read_write_token") or os.getenv("BLOB_READ_WRITE_TOKEN", "")
    if not token:
        raise RuntimeError("BLOB_READ_WRITE_TOKEN is not configured; PDF link cannot be created")

    try:
        from vercel.blob import BlobClient
    except ImportError as exc:
        raise RuntimeError("The 'vercel' package is required for PDF delivery") from exc

    timestamp = datetime.now(IST).strftime("%Y%m%d-%H%M%S")
    blob_path = f"pharma-intelligence/{date_str}/report-{timestamp}.pdf"
    uploaded = BlobClient(token=token).put(
        blob_path,
        pdf_bytes,
        access="public",
        add_random_suffix=False,
    )
    url = uploaded.url if hasattr(uploaded, "url") else uploaded.get("url", "")
    if not url:
        raise RuntimeError("PDF upload completed without returning a public URL")
    return str(url)


def _send_report_link_email(
    date_str: str,
    result: Dict[str, Any],
    pdf_url: str,
    recipients: str,
    subject: str,
) -> None:
    from crawl4ai.output.email_output import EmailOutput

    total = int(result.get("key_highlights_count", 0)) + int(result.get("other_news_count", 0))
    safe_url = escape(pdf_url, quote=True)
    html_body = f"""
    <html><body style="font-family:Arial,Helvetica,sans-serif;color:#334155;max-width:620px;margin:0 auto;padding:24px;">
      <div style="background:#0f3d52;padding:22px 26px;">
        <h2 style="margin:0;color:#ffffff;font-size:20px;">Daily Pharma Intelligence Brief</h2>
        <p style="margin:5px 0 0;color:#a8d4e0;font-size:13px;">{escape(date_str)}</p>
      </div>
      <div style="border:1px solid #dde6e9;border-top:0;padding:26px;">
        <p style="margin:0 0 18px;font-size:14px;line-height:1.6;">
          Today&apos;s pharma intelligence report is ready with <strong>{total}</strong> curated news items.
        </p>
        <p style="margin:0 0 22px;">
          <a href="{safe_url}" style="display:inline-block;background:#0f3d52;color:#ffffff;text-decoration:none;font-size:14px;font-weight:700;padding:11px 18px;">
            Download PDF Report
          </a>
        </p>
        <p style="margin:0;font-size:11px;color:#94a3b8;">Generated by IntelliFetch Pharma Intelligence Engine · Powered by Impeerical</p>
      </div>
    </body></html>
    """
    mailer = EmailOutput(to=recipients, subject=subject)
    for recipient in [value.strip() for value in recipients.split(",") if value.strip()]:
        mailer._send_via_api(recipient, html_body)


def _run_report_job(
    date_str: str,
    articles: Optional[List[PharmaArticle]] = None,
    *,
    deliver_email: bool = False,
) -> None:
    try:
        _set_run_status(date_str, "running")
        result = _generate_report(date_str, articles)
        pdf_url = None
        email_sent = False

        if deliver_email:
            cfg = _get_config()
            recipients = str(cfg.get("schedule_recipients") or "").strip()
            if not recipients:
                raise RuntimeError("Pharma schedule has no email recipients configured")
            all_items = result.get("key_highlights", []) + result.get("other_news", [])
            pdf_url = _upload_report_pdf(date_str, _build_report_pdf(date_str, all_items))
            result["pdf_url"] = pdf_url
            _store_result(date_str, result)
            subject = str(cfg.get("schedule_email_subject") or "Daily Pharma Intelligence Brief")
            _send_report_link_email(date_str, result, pdf_url, recipients, subject)
            email_sent = True

        _set_run_status(
            date_str,
            "completed",
            pdf_url=pdf_url,
            email_sent=email_sent,
        )
    except Exception as exc:
        logger.exception("[pharma-run] Report generation failed for %s", date_str)
        _set_run_status(date_str, "failed", error=str(exc))
    finally:
        with _active_runs_lock:
            _active_runs.discard(date_str)


def start_report_run(
    date_str: Optional[str] = None,
    articles: Optional[List[PharmaArticle]] = None,
    *,
    deliver_email: bool = False,
) -> bool:
    """Start a report in the background; return False when already running."""
    date_str = date_str or datetime.now(IST).date().isoformat()
    with _active_runs_lock:
        if date_str in _active_runs:
            return False
        _active_runs.add(date_str)
    try:
        _set_run_status(date_str, "pending")
        threading.Thread(
            target=_run_report_job,
            args=(date_str, articles),
            kwargs={"deliver_email": deliver_email},
            daemon=True,
            name=f"pharma-report-{date_str}",
        ).start()
        return True
    except Exception:
        with _active_runs_lock:
            _active_runs.discard(date_str)
        raise


# ── Endpoints ────────────────────────────────────────────────

@router.get("/intelligence/report")
async def get_report(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    current_user: dict = Depends(get_current_user),
):
    date_str = date or DateType.today().isoformat()
    result = await asyncio.to_thread(_get_result, date_str)
    if not result:
        raise HTTPException(
            404,
            f"No intelligence report found for {date_str}. Run POST /api/intelligence/process first.",
        )
    return JSONResponse(result)


@router.post("/intelligence/process")
async def process_articles(
    payload: ProcessRequest,
    current_user: dict = Depends(get_current_user),
):
    date_str = payload.date or DateType.today().isoformat()
    articles = (
        [_to_pharma_article(a.model_dump()) for a in payload.articles]
        if payload.articles else None
    )
    started = await asyncio.to_thread(start_report_run, date_str, articles)
    message = "Pharma intelligence generation started" if started else "A run is already in progress"
    return JSONResponse(
        {"date": date_str, "status": "pending" if started else "running", "message": message},
        status_code=202,
    )


@router.get("/intelligence/status")
async def get_process_status(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    current_user: dict = Depends(get_current_user),
):
    date_str = date or DateType.today().isoformat()
    return JSONResponse(await asyncio.to_thread(_get_run_status, date_str))


@router.get("/intelligence/config")
async def get_config(
    current_user: dict = Depends(get_current_user),
):
    cfg = await asyncio.to_thread(_get_config)
    return JSONResponse(cfg)


@router.put("/intelligence/config")
async def update_config(
    payload: KPIConfigUpdate,
    current_user: dict = Depends(get_current_user),
):
    current = await asyncio.to_thread(_get_config)
    if payload.dimension_weights is not None:
        # Merge rather than replace so a partial update (e.g. only adjusting
        # "india_torrent_relevance") doesn't zero out the other dimensions.
        current["dimension_weights"] = {
            **current.get("dimension_weights", DEFAULT_DIMENSION_WEIGHTS),
            **payload.dimension_weights,
        }
    if payload.key_highlight_score_threshold is not None:
        current["key_highlight_score_threshold"] = payload.key_highlight_score_threshold
    if payload.min_score_threshold is not None:
        current["min_score_threshold"] = payload.min_score_threshold
    if payload.schedule_enabled is not None:
        current["schedule_enabled"] = payload.schedule_enabled
    if payload.schedule_time is not None:
        try:
            datetime.strptime(payload.schedule_time, "%H:%M")
        except ValueError as exc:
            raise HTTPException(400, "schedule_time must use 24-hour HH:MM format") from exc
        current["schedule_time"] = payload.schedule_time
    if payload.schedule_recipients is not None:
        current["schedule_recipients"] = payload.schedule_recipients.strip()
    if payload.schedule_email_subject is not None:
        current["schedule_email_subject"] = payload.schedule_email_subject.strip()
    if current.get("schedule_enabled") and not current.get("schedule_recipients"):
        raise HTTPException(400, "At least one email recipient is required when scheduling is enabled")
    await asyncio.to_thread(_store_config, current)
    from dashboard.scheduler import refresh_pharma_schedule
    await asyncio.to_thread(refresh_pharma_schedule)
    return JSONResponse({"status": "ok", "config": current})


@router.get("/intelligence/report/html", response_class=HTMLResponse)
async def get_html_report(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    current_user: dict = Depends(get_current_user),
):
    date_str = date or DateType.today().isoformat()
    result = await asyncio.to_thread(_get_result, date_str)
    if not result:
        raise HTTPException(404, f"No intelligence report found for {date_str}.")
    all_items = result.get("key_highlights", []) + result.get("other_news", [])
    formatter = PharmaEmailFormatter()
    report_date = DateType.fromisoformat(date_str)
    html = await asyncio.to_thread(formatter.format_report, all_items, report_date)
    return HTMLResponse(content=html)


def _build_report_pdf(date_str: str, items: List[Dict[str, Any]]) -> bytes:
    """Render the report items into a branded PDF (for management circulation)."""
    import tempfile
    from crawl4ai.output.pdf_output import PDFReportOutput
    from crawl4ai.models import CrawlResult

    # Rank the same way the flat table does: key highlights lead, then by score.
    ranked = sorted(
        items,
        key=lambda x: (not x.get("is_key_highlight"), x.get("relevance_score", 0) * -1),
    )
    pdf_articles = [
        {
            "title": it.get("particular") or it.get("headline") or it.get("title", ""),
            "source": it.get("source") or "Multiple Sources",
            "category": it.get("primary_category") or "Pharma News",
            "summary": it.get("summary", ""),
            "time_ago": it.get("published_at", ""),
            "relevance_score": it.get("relevance_score", 0),
            "molecule": it.get("molecule"),
            "company": it.get("company"),
            "therapy_area": it.get("therapy_area"),
            "url": it.get("url", ""),
        }
        for it in ranked
    ]
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        backend = PDFReportOutput(
            path=tmp_path,
            title=f"Daily Pharma Intelligence Brief - {date_str}",
        )
        backend.save(CrawlResult(
            url="pharma-intelligence",
            success=True,
            extracted_content=json.dumps(pdf_articles),
        ))
        backend.finalize()
        with open(tmp_path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.get("/intelligence/report/pdf")
async def get_pdf_report(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    current_user: dict = Depends(get_current_user),
):
    date_str = date or DateType.today().isoformat()
    result = await asyncio.to_thread(_get_result, date_str)
    if not result:
        raise HTTPException(404, f"No intelligence report found for {date_str}.")
    all_items = result.get("key_highlights", []) + result.get("other_news", [])
    pdf_bytes = await asyncio.to_thread(_build_report_pdf, date_str, all_items)
    filename = f"pharma-intelligence-{date_str}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
