"""Job execution engine — wraps crawl4ai deep crawl pipeline."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
import traceback
from datetime import datetime, timezone, timedelta
from queue import Queue
from typing import Any, Dict, List, Optional, Set, Tuple

# IST timezone (Asia/Kolkata, UTC+5:30)
_IST = timezone(timedelta(hours=5, minutes=30))

# Set to track running job IDs and prevent duplicates
_running_jobs: Set[str] = set()

# Job queue for limiting concurrency (max 1 for Railway free tier)
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "1"))
_job_queue: Queue[Tuple[str, threading.Event]] = Queue()
_queue_processor_started = False

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
from crawl4ai.output.vercel_blob_output import VercelBlobOutput

from . import db


def _is_today_article(item: dict, today: "datetime.date") -> bool:
    """Return True if the article appears to have been published today (IST).

    Decision logic (in priority order):
    1. seconds / minutes / hours ago  → today  (hours capped at 23)
    2. "just now" / "today"           → today
    3. "yesterday" / "X day(s) ago"   → not today
    4. "week" / "month" / "year"      → not today
    5. Recognisable date string       → compare with today's date
    6. No usable date info            → include by default (don't silently drop)
    """
    raw = (
        str(item.get("time_ago") or "")
        + " "
        + str(item.get("published_date") or "")
    ).lower().strip()

    if not raw.strip():
        return True  # no date info → keep

    # ── clearly today ──────────────────────────────────────────────────────
    if re.search(r"\bjust now\b|\bmoments? ago\b|\btoday\b", raw):
        return True
    if re.search(r"\b\d+\s*s(ec(ond)?s?)?\b|\b\d+\s*min(ute)?s?\s*ago\b", raw):
        return True
    m = re.search(r"\b(\d+)\s*h(our)?s?\s*(ago)?\b", raw)
    if m:
        return int(m.group(1)) <= 23

    # ── clearly NOT today ──────────────────────────────────────────────────
    if re.search(r"\byesterday\b", raw):
        return False
    if re.search(r"\b([1-9]\d*)\s*days?\s*ago\b", raw):
        return False
    if re.search(r"\bweeks?\b|\bmonths?\b|\byears?\b", raw):
        return False

    # ── try to match a specific date ───────────────────────────────────────
    month_names = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    ]
    month_abbrs = [m[:3] for m in month_names]

    today_patterns = [
        today.strftime("%Y-%m-%d"),          # 2026-03-19
        today.strftime("%d/%m/%Y"),           # 19/03/2026
        today.strftime("%m/%d/%Y"),           # 03/19/2026
        today.strftime("%B %d, %Y").lower(),  # march 19, 2026
        today.strftime("%b %d, %Y").lower(),  # mar 19, 2026
        today.strftime("%d %B %Y").lower(),   # 19 march 2026
        today.strftime("%-d %B %Y").lower(),  # 19 march 2026 (no leading zero)
        str(today.day),                       # bare day number (last resort)
    ]
    for pat in today_patterns[:-1]:          # all except bare day
        if pat in raw:
            return True

    # If any month name appears but none of today's patterns matched → not today
    if any(m in raw for m in month_names + month_abbrs):
        return False

    # Bare day number match (only when no other month context exists)
    if today_patterns[-1] in raw:
        return True

    return True  # unknown format → keep by default


def _log(msg: str) -> None:
    """Print with flush to ensure Railway sees logs immediately."""
    print(msg, flush=True)


def _queue_processor() -> None:
    """Background thread that processes jobs from the queue with limited concurrency."""
    semaphore = threading.Semaphore(MAX_CONCURRENT_JOBS)
    
    while True:
        try:
            job_id, done_event = _job_queue.get(timeout=1)
            if job_id is None:  # Shutdown signal
                break
                
            # Try to acquire semaphore (blocks until slot available)
            acquired = semaphore.acquire(blocking=False)
            if not acquired:
                _log(f"[engine] Job {job_id} waiting for available slot ({MAX_CONCURRENT_JOBS} max)")
                semaphore.acquire()  # Block until available
                
            # Run the job in a thread
            def run_with_release():
                try:
                    _run_in_thread(job_id)
                finally:
                    semaphore.release()
                    done_event.set()
                    
            thread = threading.Thread(target=run_with_release, daemon=True)
            thread.start()
            
        except Exception:
            continue


def _start_queue_processor() -> None:
    """Start the queue processor thread if not already running."""
    global _queue_processor_started
    if not _queue_processor_started:
        processor = threading.Thread(target=_queue_processor, daemon=True)
        processor.start()
        _queue_processor_started = True
        _log(f"[engine] Queue processor started (max_concurrent={MAX_CONCURRENT_JOBS})")


def run_job_async(job_id: str) -> None:
    """Queue a crawl job for execution with limited concurrency.
    
    Jobs are processed FIFO with MAX_CONCURRENT_JOBS limit.
    Prevents duplicate execution of the same job ID.
    """
    global _running_jobs, _queue_processor_started
    
    # Check if job is already running
    if job_id in _running_jobs:
        print(f"[engine] Job {job_id} is already running, skipping duplicate execution")
        return
        
    # Mark job as running and queue it
    _running_jobs.add(job_id)
    _start_queue_processor()
    
    done_event = threading.Event()
    _job_queue.put((job_id, done_event))
    
    queue_size = _job_queue.qsize()
    if queue_size > 1:
        print(f"[engine] Job {job_id} queued (position {queue_size}, max_concurrent={MAX_CONCURRENT_JOBS})")
    else:
        print(f"[engine] Job {job_id} queued for execution")


def _run_in_thread(job_id: str) -> None:
    """Thread target: create a new event loop and run the async job."""
    global _running_jobs
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    JOB_TIMEOUT = 600  # 10 minutes max per job
    try:
        loop.run_until_complete(
            asyncio.wait_for(_execute_job(job_id), timeout=JOB_TIMEOUT)
        )
        _log(f"[engine] Job {job_id} thread completed successfully")
    except asyncio.TimeoutError:
        _log(f"[engine] Job {job_id} TIMED OUT after {JOB_TIMEOUT}s")
        try:
            db.update_job(job_id, status="failed", finished_at=datetime.now().isoformat(),
                          error=f"Job timed out after {JOB_TIMEOUT} seconds")
        except Exception:
            pass
    except Exception as exc:
        _log(f"[engine] Job {job_id} thread FAILED: {exc}")
        _log(f"[engine] Traceback: {traceback.format_exc()}")
        try:
            db.update_job(job_id, status="failed", error=traceback.format_exc())
        except Exception:
            pass
    finally:
        # Remove job from running set when complete
        _running_jobs.discard(job_id)
        loop.close()


async def _execute_job(job_id: str) -> None:
    """Core async job execution."""
    job = db.get_job(job_id)
    if not job:
        print(f"[engine] Job {job_id} not found in database, skipping execution")
        return

    config = json.loads(job["config"]) if isinstance(job["config"], str) else job["config"]
    url = job["url"]

    _log(f"[engine] Job {job_id} starting for URL: {url}")
    db.update_job(job_id, status="running", started_at=datetime.now().isoformat())

    # Load settings for API keys
    settings = db.get_all_settings()
    groq_key = settings.get("groq_api_key", os.getenv("GROQ_API_KEY", ""))

    # Build output directory with absolute path to avoid relative path issues
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    output_dir = os.path.join(project_root, "output", job_id)
    os.makedirs(output_dir, exist_ok=True)
    db.update_job(job_id, output_dir=output_dir)

    # Build output backends
    recipients = config.get("recipients", "")
    email_subject = config.get("email_subject") or f"IntelliFetch News Digest: {job['name']}"

    _, _, outputs = create_job_outputs(
        project_root=project_root,
        job_id=job_id,
        title=job["name"],
        email_to=recipients if recipients else None,
        email_subject=email_subject,
    )

    # Vercel Blob Storage — upload artifacts after local backends write them
    blob_token = settings.get("blob_read_write_token", os.getenv("BLOB_READ_WRITE_TOKEN", ""))
    blob_backend = VercelBlobOutput(
        job_id=job_id,
        output_dir=output_dir,
        blob_token=blob_token,
    )
    outputs.append(blob_backend)

    backend_names = [type(b).__name__ for b in outputs]
    print(f"[engine] Job {job_id}: backends={backend_names}")
    print(f"[engine]   recipients={recipients!r}")

    # Browser config
    browser_conf = BrowserConfig(
        headless=True,
        stealth_mode=config.get("stealth", True),
        simulate_human=config.get("simulate_human", True),
        block_images=config.get("block_images", True),
    )

    # Today's date in IST — used in the extraction instruction and post-filter
    today_ist = datetime.now(_IST)
    today_str = today_ist.strftime("%B %-d, %Y")  # e.g. "March 19, 2026"

    # Schema fields
    schema_fields = config.get("schema_fields", {})
    if not schema_fields:
        schema_fields = {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The news headline"},
                "source": {"type": "string", "description": "Publisher name"},
                "category": {"type": "string", "description": "Topic category"},
                "summary": {"type": "string", "description": "One-sentence summary"},
                "time_ago": {"type": "string", "description": "How long ago it was published, e.g. '2 hours ago', '30 minutes ago'"},
                "published_date": {"type": "string", "description": "The publication date if explicitly shown, e.g. 'March 19, 2026' or '2026-03-19'"},
            },
            "required": ["title"],
        }

    # LLM extraction
    default_instruction = (
        f"Today's date is {today_str} (IST, Asia/Kolkata). "
        f"Extract ONLY actual news articles that were published TODAY ({today_str}). "
        "DO NOT include articles from yesterday or any earlier date. "
        "Ignore ads, promotions, newsletters, events, navigation links, and category labels. "
        "For each article include: title, source, category, summary, time_ago (e.g. '2 hours ago'), "
        "and published_date (the exact date shown on the article, if visible). "
        "If an article has no visible publication date or time, include it only if it appears to be recent/today. "
        "Return a JSON array containing only today's articles."
    )
    extraction = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider=config.get("llm_provider", "groq/llama-3.1-8b-instant"),
            api_token=groq_key,
        ),
        schema=schema_fields,
        extraction_type="schema",
        instruction=config.get("extraction_instruction") or default_instruction,
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
        _log(f"[engine] Job {job_id} step 1/5: launching browser...")
        async with AsyncWebCrawler(config=browser_conf) as crawler:
            _log(f"[engine] Job {job_id} step 2/5: deep_crawl starting...")
            deep_result = await deep_crawl(crawler, url, deep_conf, run_conf)
            all_content = deep_result["all_content"]

            # Log crawl outcome for debugging
            listing = deep_result.get("listing_result")
            if listing and not listing.success:
                _log(f"[engine] Listing page failed: {listing.error_message}")
            content_len = len(all_content.strip()) if all_content else 0
            _log(f"[engine] Job {job_id} step 3/5: deep_crawl done, content={content_len} chars")
            if content_len == 0:
                _log(f"[engine] WARNING: deep_crawl returned empty content for {url}")

            # Smart extraction with noise filtering
            _log(f"[engine] Job {job_id} step 4/5: smart_extract starting...")
            extracted = await smart_extract(
                all_content, run_conf, deep_conf.filter_instruction
            )
            _log(f"[engine] Job {job_id} step 4/5: smart_extract done")

        # Parse and count articles
        from crawl4ai.output.email_output import EmailOutput as EO
        articles = EO._parse_extracted(extracted)

        # ── Today-only post-filter (safety net on top of LLM instruction) ──
        if isinstance(articles, list) and articles:
            today_date = today_ist.date()
            before_count = len(articles)
            articles = [
                a for a in articles
                if isinstance(a, dict) and _is_today_article(a, today_date)
            ]
            dropped = before_count - len(articles)
            if dropped:
                _log(f"[engine] Job {job_id}: post-filter dropped {dropped} non-today articles "
                     f"({len(articles)} remain for {today_str})")
            # Re-serialise filtered list so it's what gets stored & emailed
            extracted = json.dumps(articles)

        article_count = len(articles) if isinstance(articles, list) else 0
        _log(f"[engine] Job {job_id} step 5/5: saving {article_count} articles to outputs...")

        # Generate AI summary if requested and articles are available
        if config.get("summarize_with_ai") and article_count > 0 and groq_key:
            try:
                import litellm
                article_lines = []
                for art in (articles if isinstance(articles, list) else [])[:25]:
                    if isinstance(art, dict):
                        title = art.get("title", "")
                        summary = art.get("summary", "")
                        article_lines.append(f"- {title}: {summary}" if summary else f"- {title}")
                articles_text = "\n".join(article_lines)
                summary_prompt = (
                    f"Based on these {article_count} scraped articles, write a concise 2-3 sentence "
                    f"executive summary covering the main themes and key topics:\n\n{articles_text}"
                )
                summary_response = await litellm.acompletion(
                    model=config.get("llm_provider", "groq/llama-3.1-8b-instant"),
                    api_key=groq_key,
                    messages=[
                        {"role": "system", "content": "You are a news analyst. Write clear, concise executive summaries."},
                        {"role": "user", "content": summary_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=200,
                )
                ai_summary = summary_response.choices[0].message.content.strip()
                # Inject the summary into the EmailOutput backend
                for output in outputs:
                    if isinstance(output, EO):
                        output.ai_summary = ai_summary
                        break
                _log(f"[engine] Job {job_id}: AI summary generated ({len(ai_summary)} chars)")
            except Exception as summary_err:
                _log(f"[engine] Job {job_id}: AI summary generation failed: {summary_err}")

        # Save final result through output backends (skip email if no articles)
        final_result = CrawlResult(
            url=url,
            success=article_count > 0,
            markdown=MarkdownResult(raw_markdown=all_content[:5000]),
            extracted_content=extracted if isinstance(extracted, str) else json.dumps(extracted),
        )
        manager = OutputManager(outputs)
        manager.save(final_result)
        manager.finalize()

        status = "completed" if article_count > 0 else "completed_empty"
        update_kwargs: dict = {
            "status": status,
            "finished_at": datetime.now().isoformat(),
            "article_count": article_count,
        }
        # Persist extracted articles for consolidated report retrieval
        if isinstance(articles, list) and article_count > 0:
            update_kwargs["extracted_articles"] = articles
        if blob_backend.uploaded_urls:
            update_kwargs["blob_urls"] = blob_backend.uploaded_urls
            _log(f"[engine] Job {job_id}: blob URLs stored: {blob_backend.uploaded_urls}")
        db.update_job(job_id, **update_kwargs)
        _log(f"[engine] Job {job_id} DONE: status={status}, articles={article_count}")

    except Exception as exc:
        _log(f"[engine] Job {job_id} EXCEPTION: {exc}")
        _log(f"[engine] {traceback.format_exc()}")
        db.update_job(
            job_id,
            status="failed",
            finished_at=datetime.now().isoformat(),
            error=traceback.format_exc(),
        )
        raise
