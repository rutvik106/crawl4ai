"""Pharma Intelligence API router.

Routes (all under /api prefix from main.py):
  GET  /api/intelligence/report       - fetch stored result for a date
  POST /api/intelligence/process      - run pipeline, store result
  GET  /api/intelligence/config       - read KPI config
  PUT  /api/intelligence/config       - update KPI config
  GET  /api/intelligence/report/html  - HTML email report
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from datetime import date as DateType
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from api.auth import get_current_user
from crawl4ai.pharma_intelligence import (
    PharmaArticle,
    PharmaEmailFormatter,
    PharmaPipeline,
)
from crawl4ai.pharma_intelligence.ontology import (
    KEY_HIGHLIGHT_SCORE_THRESHOLD,
    KPI_WEIGHTS,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pharma-intelligence"])

# SQLite file stored at project root
_DB_PATH = os.environ.get(
    "PHARMA_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "pharma_intelligence.db"),
)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pharma_results (
            date_key TEXT PRIMARY KEY,
            result_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pharma_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            config_json TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


_init_db()


# ── SQLite helpers (sync, called via asyncio.to_thread) ────────────────────────

def _get_result(date_str: str) -> Optional[Dict]:
    conn = _get_conn()
    row = conn.execute("SELECT result_json FROM pharma_results WHERE date_key = ?", (date_str,)).fetchone()
    conn.close()
    return json.loads(row["result_json"]) if row else None


def _store_result(date_str: str, result: Dict) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO pharma_results (date_key, result_json) VALUES (?, ?)",
        (date_str, json.dumps(result)),
    )
    conn.commit()
    conn.close()


def _get_config() -> Dict:
    conn = _get_conn()
    row = conn.execute("SELECT config_json FROM pharma_config WHERE id = 1").fetchone()
    conn.close()
    if row:
        return json.loads(row["config_json"])
    return {
        "kpi_weights": KPI_WEIGHTS,
        "key_highlight_score_threshold": KEY_HIGHLIGHT_SCORE_THRESHOLD,
        "min_score_threshold": 10,
    }


def _store_config(cfg: Dict) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO pharma_config (id, config_json) VALUES (1, ?)",
        (json.dumps(cfg),),
    )
    conn.commit()
    conn.close()


# ── LLM client (reads OPENAI_API_KEY env var; falls back to rule-based) ────────────

def _make_llm_client() -> Optional[Callable[[str, str], str]]:
    try:
        import openai
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None
        model = os.environ.get("PHARMA_LLM_MODEL", "gpt-4o-mini")
        client = openai.OpenAI(api_key=api_key)

        def call_llm(system: str, user: str) -> str:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.1,
                max_tokens=1024,
            )
            return resp.choices[0].message.content or ""

        return call_llm
    except Exception:
        return None


# ── Request models ───────────────────────────────────────────────────────────

class ArticleInput(BaseModel):
    title: str
    text: str
    summary: Optional[str] = None
    url: str
    source: Optional[str] = None
    published_at: Optional[str] = None
    category: Optional[str] = None


class ProcessRequest(BaseModel):
    articles: List[ArticleInput]
    date: Optional[str] = None  # YYYY-MM-DD, defaults to today


class KPIConfigUpdate(BaseModel):
    kpi_weights: Optional[Dict[str, int]] = None
    key_highlight_score_threshold: Optional[int] = None
    min_score_threshold: Optional[int] = None


# ── Endpoints ────────────────────────────────────────────────────────────

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
    if not payload.articles:
        raise HTTPException(400, "No articles provided")

    date_str = payload.date or DateType.today().isoformat()
    pharma_cfg = await asyncio.to_thread(_get_config)
    min_score = pharma_cfg.get("min_score_threshold", 10)

    pipeline = PharmaPipeline(
        llm_client=_make_llm_client(),
        min_score_threshold=min_score,
        run_deduplication=True,
    )

    articles = [
        PharmaArticle(
            title=a.title, text=a.text, summary=a.summary or "",
            url=a.url, source=a.source or "",
            published_at=a.published_at or "", category=a.category or "",
        )
        for a in payload.articles
    ]

    results = await asyncio.to_thread(pipeline.process, articles)

    formatter = PharmaEmailFormatter()
    all_items = [r.to_dict() for r in results]
    summary = formatter.format_json_summary(all_items)
    summary["generated_at"] = date_str
    summary["excluded_count"] = len(payload.articles) - len(results)

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
