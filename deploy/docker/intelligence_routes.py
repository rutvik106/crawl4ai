"""
Pharma Intelligence API routes

GET  /intelligence/report        - fetch stored results for a date
POST /intelligence/process       - run pipeline on articles, store result
GET  /intelligence/config        - read KPI config from Redis
PUT  /intelligence/config        - update KPI config in Redis
GET  /intelligence/report/html   - return HTML email report
"""

import asyncio
import json
import logging
import os
from datetime import date as DateType
from typing import Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

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

# ── shared singletons injected by server.py ──────────────────────────────
_redis = None
_config = None
_token_dep: Callable = lambda: None

router = APIRouter(prefix="/intelligence", tags=["pharma-intelligence"])

REDIS_RESULT_PREFIX = "pharma:result:"
REDIS_CONFIG_KEY = "pharma:config"
RESULT_TTL = 60 * 60 * 24 * 7  # 7 days


def init_intelligence_router(redis, config, token_dep) -> APIRouter:
    global _redis, _config, _token_dep
    _redis, _config, _token_dep = redis, config, token_dep
    return router


# ── LLM client factory ───────────────────────────────────────────────────
def _make_llm_client() -> Optional[Callable[[str, str], str]]:
    """Build a sync LLM callable from server config, or None for rule-based fallback."""
    try:
        import openai

        llm_cfg = (_config or {}).get("llm", {})
        api_key = llm_cfg.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None

        model = llm_cfg.get("model", "gpt-4o-mini")
        client = openai.OpenAI(api_key=api_key)

        def call_llm(system: str, user: str) -> str:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.1,
                max_tokens=1024,
            )
            return resp.choices[0].message.content or ""

        return call_llm
    except Exception:
        return None


# ── Redis helpers ────────────────────────────────────────────────────────
async def _get_result(date_str: str) -> Optional[Dict]:
    raw = await _redis.get(f"{REDIS_RESULT_PREFIX}{date_str}")
    return json.loads(raw) if raw else None


async def _store_result(date_str: str, result: Dict) -> None:
    await _redis.setex(
        f"{REDIS_RESULT_PREFIX}{date_str}",
        RESULT_TTL,
        json.dumps(result),
    )


async def _get_pharma_config() -> Dict:
    raw = await _redis.get(REDIS_CONFIG_KEY)
    if raw:
        return json.loads(raw)
    return {
        "kpi_weights": KPI_WEIGHTS,
        "key_highlight_score_threshold": KEY_HIGHLIGHT_SCORE_THRESHOLD,
        "min_score_threshold": 10,
    }


async def _store_pharma_config(cfg: Dict) -> None:
    await _redis.set(REDIS_CONFIG_KEY, json.dumps(cfg))


# ── Request / Response models ────────────────────────────────────────────
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
@router.get("/report")
async def get_report(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    _td: Dict = Depends(lambda: _token_dep()),
):
    date_str = date or DateType.today().isoformat()
    result = await _get_result(date_str)
    if not result:
        raise HTTPException(
            404,
            f"No intelligence report found for {date_str}. "
            "Run POST /intelligence/process first.",
        )
    return JSONResponse(result)


@router.post("/process")
async def process_articles(
    payload: ProcessRequest,
    _td: Dict = Depends(lambda: _token_dep()),
):
    if not payload.articles:
        raise HTTPException(400, "No articles provided")

    date_str = payload.date or DateType.today().isoformat()
    pharma_cfg = await _get_pharma_config()
    min_score = pharma_cfg.get("min_score_threshold", 10)

    llm_client = _make_llm_client()
    pipeline = PharmaPipeline(
        llm_client=llm_client,
        min_score_threshold=min_score,
        run_deduplication=True,
    )

    articles = [
        PharmaArticle(
            title=a.title,
            text=a.text,
            summary=a.summary or "",
            url=a.url,
            source=a.source or "",
            published_at=a.published_at or "",
            category=a.category or "",
        )
        for a in payload.articles
    ]

    # Run sync pipeline in thread pool to avoid blocking the event loop
    result = await asyncio.to_thread(pipeline.process, articles)
    result_dict = result.to_dict()

    await _store_result(date_str, result_dict)
    return JSONResponse(result_dict)


@router.get("/config")
async def get_config(
    _td: Dict = Depends(lambda: _token_dep()),
):
    cfg = await _get_pharma_config()
    return JSONResponse(cfg)


@router.put("/config")
async def update_config(
    payload: KPIConfigUpdate,
    _td: Dict = Depends(lambda: _token_dep()),
):
    current = await _get_pharma_config()
    if payload.kpi_weights is not None:
        current["kpi_weights"] = payload.kpi_weights
    if payload.key_highlight_score_threshold is not None:
        current["key_highlight_score_threshold"] = payload.key_highlight_score_threshold
    if payload.min_score_threshold is not None:
        current["min_score_threshold"] = payload.min_score_threshold
    await _store_pharma_config(current)
    return JSONResponse({"status": "ok", "config": current})


@router.get("/report/html", response_class=HTMLResponse)
async def get_html_report(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    _td: Dict = Depends(lambda: _token_dep()),
):
    date_str = date or DateType.today().isoformat()
    result = await _get_result(date_str)
    if not result:
        raise HTTPException(
            404,
            f"No intelligence report found for {date_str}.",
        )

    formatter = PharmaEmailFormatter()
    html = await asyncio.to_thread(_render_html, formatter, result)
    return HTMLResponse(content=html)


def _render_html(formatter: PharmaEmailFormatter, result: Dict) -> str:
    """Reconstruct a result-compatible object and render HTML."""

    class _Result:
        def __init__(self, d: Dict):
            self.key_highlights = d.get("key_highlights", [])
            self.other_news = d.get("other_news", [])
            self.total_articles_processed = d.get("total_articles_processed", 0)
            self.key_highlights_count = d.get("key_highlights_count", 0)
            self.other_news_count = d.get("other_news_count", 0)
            self.excluded_count = d.get("excluded_count", 0)
            self.generated_at = d.get("generated_at", "")

    return formatter.format_report(_Result(result))
