"""Job execution engine — wraps crawl4ai deep crawl pipeline."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

# Ensure crawl4ai is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env for fallback credentials
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    LLMConfig,
    LLMExtractionStrategy,
    CrawlResult,
    MarkdownResult,
    DeepCrawlConfig,
    deep_crawl,
    smart_extract,
)
from crawl4ai.output.job import create_job_outputs, generate_job_id
from crawl4ai.output.base import OutputManager

from . import db


def run_job_async(job_id: str) -> None:
    """Run a crawl job in a background thread with its own event loop."""
    thread = threading.Thread(target=_run_in_thread, args=(job_id,), daemon=True)
    thread.start()


def _run_in_thread(job_id: str) -> None:
    """Thread target: create a new event loop and run the async job."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_execute_job(job_id))
    except Exception as exc:
        db.update_job(job_id, status="failed", error=str(exc))
    finally:
        loop.close()


async def _execute_job(job_id: str) -> None:
    """Core async job execution."""
    job = db.get_job(job_id)
    if not job:
        return

    config = json.loads(job["config"]) if isinstance(job["config"], str) else job["config"]
    url = job["url"]

    db.update_job(job_id, status="running", started_at=datetime.now().isoformat())

    # Load settings for API keys and SMTP
    settings = db.get_all_settings()
    groq_key = settings.get("groq_api_key", os.getenv("GROQ_API_KEY", ""))
    smtp_host = settings.get("smtp_host", os.getenv("SMTP_HOST", ""))
    smtp_port = int(settings.get("smtp_port", os.getenv("SMTP_PORT", "587")))
    smtp_user = settings.get("smtp_user", os.getenv("SMTP_USER", ""))
    smtp_password = settings.get("smtp_password", os.getenv("SMTP_PASSWORD", ""))

    # Build output directory
    project_root = os.path.join(os.path.dirname(__file__), "..")
    output_dir = os.path.join(project_root, "output", job_id)
    os.makedirs(output_dir, exist_ok=True)
    db.update_job(job_id, output_dir=output_dir)

    # Build output backends
    recipients = config.get("recipients", "")
    email_subject = config.get("email_subject", f"Impeerical 4 AI: {job['name']}")

    _, _, outputs = create_job_outputs(
        project_root=project_root,
        job_id=job_id,
        title=job["name"],
        email_to=recipients if recipients else None,
        smtp_host=smtp_host if recipients else None,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        email_subject=email_subject,
    )

    backend_names = [type(b).__name__ for b in outputs]
    print(f"[engine] Job {job_id}: backends={backend_names}")
    print(f"[engine]   recipients={recipients!r}, smtp_host={smtp_host!r}, smtp_user={smtp_user!r}")

    # Browser config
    browser_conf = BrowserConfig(
        headless=True,
        stealth_mode=config.get("stealth", True),
        simulate_human=config.get("simulate_human", True),
        block_images=config.get("block_images", True),
    )

    # Schema fields
    schema_fields = config.get("schema_fields", {})
    if not schema_fields:
        schema_fields = {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The news headline"},
                "source": {"type": "string", "description": "Publisher name"},
                "category": {"type": "string", "description": "Category"},
                "summary": {"type": "string", "description": "One-sentence summary"},
            },
            "required": ["title"],
        }

    # LLM extraction
    extraction = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider=config.get("llm_provider", "groq/llama-3.1-8b-instant"),
            api_token=groq_key,
        ),
        schema=schema_fields,
        extraction_type="schema",
        instruction=config.get("extraction_instruction", (
            "Extract ONLY actual news articles. Ignore ads, promos, newsletters, "
            "events, navigation, category labels. For each article, get title, source, "
            "category, and summary. Return a JSON array."
        )),
        extra_args={"temperature": 0, "max_tokens": 4000},
        content_length_limit=int(config.get("content_limit", 12000)),
    )

    run_conf = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction,
    )

    # Deep crawl config
    deep_conf = DeepCrawlConfig(
        scroll=config.get("scroll", True),
        max_scrolls=int(config.get("max_scrolls", 10)),
        scroll_delay=float(config.get("scroll_delay", 1.0)),
        click_load_more=config.get("click_load_more", True),
        follow_links=config.get("follow_links", True),
        link_selector=config.get("link_selector", "a[href]"),
        link_filter_pattern=config.get("link_filter", ""),
        max_inner_pages=int(config.get("max_inner_pages", 5)),
        use_screenshots=config.get("screenshots", True),
        screenshot_dir=os.path.join(output_dir, "screenshots"),
        smart_filter=config.get("smart_filter", True),
    )

    try:
        async with AsyncWebCrawler(config=browser_conf) as crawler:
            deep_result = await deep_crawl(crawler, url, deep_conf, run_conf)
            all_content = deep_result["all_content"]

            # Smart extraction with noise filtering
            extracted = await smart_extract(
                all_content, run_conf, deep_conf.filter_instruction
            )

        # Parse and count articles
        from crawl4ai.output.email_output import EmailOutput as EO
        articles = EO._parse_extracted(extracted)
        article_count = len(articles) if isinstance(articles, list) else 0

        # Save final result through output backends
        final_result = CrawlResult(
            url=url,
            success=True,
            markdown=MarkdownResult(raw_markdown=all_content[:5000]),
            extracted_content=extracted if isinstance(extracted, str) else json.dumps(extracted),
        )
        manager = OutputManager(outputs)
        manager.save(final_result)
        manager.finalize()

        db.update_job(
            job_id,
            status="completed",
            finished_at=datetime.now().isoformat(),
            article_count=article_count,
        )

    except Exception as exc:
        db.update_job(
            job_id,
            status="failed",
            finished_at=datetime.now().isoformat(),
            error=traceback.format_exc(),
        )
        raise
