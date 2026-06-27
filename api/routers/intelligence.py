"""Pharma Intelligence API router.

Routes (all under /api prefix from main.py):
  GET  /api/intelligence/report       - fetch stored result for a date
  POST /api/intelligence/process      - run pipeline on crawled articles for a date
  GET  /api/intelligence/config       - read KPI config
  PUT  /api/intelligence/config       - update KPI config
  GET  /api/intelligence/report/html  - HTML email report

Storage is PostgreSQL (same DATABASE_URL as dashboard/db.py) so results and
config survive restarts on Railway/Neon. Articles are pulled from already-
crawled jobs (jobs.extracted_articles) for the requested date.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date as DateType, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from api.auth import get_current_user
from crawl4ai.pharma_intelligence import (
    IST,
    PharmaArticle,
    PharmaEmailFormatter,
    PharmaPipeline,
    is_within_last_24h,
)
from crawl4ai.pharma_intelligence.ontology import (
    KEY_HIGHLIGHT_SCORE_THRESHOLD,
    KPI_WEIGHTS,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pharma-intelligence"])

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/crawl4ai_dashboard",
)

DEFAULT_CONFIG: Dict[str, Any] = {
    "kpi_weights": KPI_WEIGHTS,
    "key_highlight_score_threshold": KEY_HIGHLIGHT_SCORE_THRESHOLD,
    "min_score_threshold": 10,
    "bundle_configs": {
        "regulatory_agencies": {"enabled": True, "kpi_focus": ["approval", "label_expansion"]},
        "pharma_news": {"enabled": True, "kpi_focus": ["ma", "licensing", "clinical_outcome"]},
        "clinical_trials": {"enabled": True, "kpi_focus": ["clinical_outcome"]},
        "patent_ip": {"enabled": True, "kpi_focus": ["patent"]},
        "corporate_pr": {"enabled": True, "kpi_focus": ["ma", "licensing"]},
    },
}

_COMPLETED_STATUSES = ("completed", "completed_empty")
_tables_ready = False


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
    # Merge with defaults so new keys (like bundle_configs) are always present
    merged = dict(DEFAULT_CONFIG)
    merged.update(stored)
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
    url = (a.get("url") or a.get("link") or a.get("source_url") or "").strip()
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
        return None

    try:
        import litellm
    except Exception:
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

    return call_llm


def _make_anthropic_client() -> Optional[Callable[[str, str], str]]:
    """Native Anthropic Claude adapter.

    Claude takes the system prompt as a top-level argument (not a message role),
    so we map our (system, user) signature accordingly. Reads ANTHROPIC_API_KEY
    and PHARMA_LLM_MODEL (defaults to a current Claude model).
    """
    try:
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        model = os.environ.get("PHARMA_LLM_MODEL", "claude-3-5-sonnet-latest")
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

        return call_llm
    except Exception:
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
    kpi_weights: Optional[Dict[str, int]] = None
    key_highlight_score_threshold: Optional[int] = None
    min_score_threshold: Optional[int] = None
    bundle_configs: Optional[Dict[str, Any]] = None


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

    # Articles come from the request body when provided (testing/override),
    # otherwise from already-crawled jobs for the date.
    if payload.articles:
        articles = [_to_pharma_article(a.model_dump()) for a in payload.articles]
    else:
        articles = await asyncio.to_thread(_fetch_articles_for_date, date_str)

    if not articles:
        raise HTTPException(
            404,
            f"No crawled articles found for {date_str}. Run a crawl job for this date first.",
        )

    pharma_cfg = await asyncio.to_thread(_get_config)
    min_score = pharma_cfg.get("min_score_threshold", 10)

    pipeline = PharmaPipeline(
        llm_client=_make_llm_client(),
        min_score_threshold=min_score,
        run_deduplication=True,
    )

    results = await asyncio.to_thread(pipeline.process, articles)

    formatter = PharmaEmailFormatter()
    all_items = [r.to_dict() for r in results]
    summary = formatter.format_json_summary(all_items)
    summary["generated_at"] = date_str
    # Never-drop policy: no article is discarded. The only reduction in count comes
    # from de-duplication (multiple sources merged into one consolidated item).
    summary["demoted_count"] = sum(1 for r in results if r.demoted)
    summary["consolidated_count"] = len(articles) - len(results)
    summary["excluded_count"] = 0  # retained for backward compatibility

    await asyncio.to_thread(_store_result, date_str, summary)
    return JSONResponse(summary)


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
    if payload.kpi_weights is not None:
        current["kpi_weights"] = payload.kpi_weights
    if payload.key_highlight_score_threshold is not None:
        current["key_highlight_score_threshold"] = payload.key_highlight_score_threshold
    if payload.min_score_threshold is not None:
        current["min_score_threshold"] = payload.min_score_threshold
    if payload.bundle_configs is not None:
        current["bundle_configs"] = payload.bundle_configs
    await asyncio.to_thread(_store_config, current)
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
    html = await asyncio.to_thread(formatter.format_report, all_items)
    return HTMLResponse(content=html)
