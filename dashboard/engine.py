"""Job execution engine — wraps crawl4ai deep crawl pipeline."""

from __future__ import annotations

import asyncio
import copy
import difflib
import json
import os
import re
import sys
import threading
import traceback
import unicodedata
from datetime import datetime, timezone, timedelta
from queue import Queue
from typing import Any, Dict, List, Optional, Set, Tuple

# IST timezone (Asia/Kolkata, UTC+5:30)
_IST = timezone(timedelta(hours=5, minutes=30))

# Set to track running job IDs and prevent duplicates
_running_jobs: Set[str] = set()

# Job queue for limiting concurrency (max 1 for Railway free tier)
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "3"))
HARD_THREAD_TIMEOUT = int(os.getenv("HARD_THREAD_TIMEOUT", "900"))  # 15 min safety net
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
from crawl4ai.pharma_intelligence.recency import is_within_last_24h

from . import db


def _log(msg: str) -> None:
    """Print with flush to ensure Railway sees logs immediately."""
    print(msg, flush=True)


def _normalise_headline(value: Any) -> str:
    """Return a comparison-friendly headline without changing stored text."""
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def _attach_article_urls(
    articles: List[Dict[str, Any]],
    article_links: List[Dict[str, Any]],
) -> int:
    """Attach crawler-discovered URLs to extracted articles by headline.

    The crawler already knows the exact destination for every listing link. The
    LLM is still asked to return ``url``, but this deterministic reconciliation
    prevents a missing model field from erasing the source link.
    """
    candidates = []
    for link in article_links or []:
        if not isinstance(link, dict):
            continue
        url = str(link.get("url") or "").strip()
        headline = _normalise_headline(link.get("text"))
        if url.startswith(("http://", "https://")) and headline:
            candidates.append((headline, url))

    attached = 0
    used_urls: Set[str] = set()
    for article in articles:
        if not isinstance(article, dict):
            continue

        existing = str(
            article.get("url")
            or article.get("link")
            or article.get("source_url")
            or article.get("article_url")
            or article.get("href")
            or ""
        ).strip()
        if existing.startswith(("http://", "https://")):
            article["url"] = existing
            used_urls.add(existing)
            continue

        title = _normalise_headline(article.get("title"))
        if not title:
            continue

        best_url = ""
        best_score = 0.0
        title_words = set(title.split())
        for link_title, link_url in candidates:
            if link_url in used_urls:
                continue
            if title == link_title:
                best_url, best_score = link_url, 1.0
                break

            link_words = set(link_title.split())
            common_words = title_words & link_words
            if len(common_words) < 4:
                continue
            score = difflib.SequenceMatcher(None, title, link_title).ratio()
            if score > best_score:
                best_url, best_score = link_url, score

        if best_url and best_score >= 0.78:
            article["url"] = best_url
            used_urls.add(best_url)
            attached += 1

    return attached


# Default extraction model. Claude Sonnet has far higher recall than the old
# Groq 8B model and reads publication dates reliably, which directly reduces
# the "dropped / missing news" problem. Resolved via litellm.
DEFAULT_LLM_PROVIDER = "anthropic/claude-sonnet-4-5"


def _resolve_llm_key(provider: str, settings: Dict[str, str]) -> str:
    """Pick the correct API key for a litellm provider string.

    ``provider`` is a litellm model id such as ``anthropic/claude-sonnet-4-5``,
    ``groq/llama-3.1-8b-instant`` or ``openai/gpt-4o``. Each provider needs its
    own key, so we resolve by prefix: DB setting first, then environment var.
    Previously the Groq key was hardcoded for every provider, which silently
    broke any non-Groq model.
    """
    p = (provider or "").lower()

    def _pick(setting_key: str, env_key: str) -> str:
        return settings.get(setting_key, "") or os.getenv(env_key, "")

    if p.startswith("anthropic/") or "claude" in p:
        return _pick("anthropic_api_key", "ANTHROPIC_API_KEY")
    if p.startswith("openai/") or p.startswith("gpt"):
        return _pick("openai_api_key", "OPENAI_API_KEY")
    if p.startswith("ollama"):
        return ""  # local, no key needed
    # Default / back-compat: Groq
    return _pick("groq_api_key", "GROQ_API_KEY")


def _resolve_proxy(settings: Dict[str, str]) -> Optional[Dict[str, str]]:
    """Build a Playwright proxy config from stored credentials, or None.

    Used for BrightData Web Unlocker (an authenticated proxy endpoint that
    transparently solves anti-bot challenges, e.g. for businesswire.com). The
    returned dict is passed straight to Playwright's launch ``proxy`` option.
    Reads DB settings first, then PROXY_* env vars.
    """
    def _pick(setting_key: str, env_key: str) -> str:
        return (settings.get(setting_key, "") or os.getenv(env_key, "")).strip()

    server = _pick("proxy_server", "PROXY_SERVER")
    if not server:
        return None
    # Normalise to a URL Playwright accepts (defaults to http:// if no scheme).
    if "://" not in server:
        server = "http://" + server
    proxy: Dict[str, str] = {"server": server}
    username = _pick("proxy_username", "PROXY_USERNAME")
    password = _pick("proxy_password", "PROXY_PASSWORD")
    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password
    return proxy


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

            # IMPORTANT: capture job_id and done_event as default-arg values so that
            # the closure is not affected when the while-loop overwrites those variables
            # on the next iteration before this thread has had a chance to run.
            def run_with_release(_jid=job_id, _ev=done_event):
                try:
                    _run_in_thread(_jid)
                finally:
                    semaphore.release()
                    _ev.set()

            thread = threading.Thread(target=run_with_release, daemon=True)
            thread.start()

            # Hard timeout watchdog: if the thread doesn't finish in time,
            # mark the job as failed and release resources so other jobs
            # aren't blocked forever.
            def _watchdog(_t=thread, _jid=job_id, _ev=done_event):
                _t.join(timeout=HARD_THREAD_TIMEOUT)
                if _t.is_alive():
                    _log(f"[engine] WATCHDOG: Job {_jid} exceeded {HARD_THREAD_TIMEOUT}s hard timeout, marking failed")
                    try:
                        db.update_job(
                            _jid, status="failed",
                            finished_at=datetime.now().isoformat(),
                            error=f"Job exceeded hard timeout of {HARD_THREAD_TIMEOUT}s and was terminated.",
                        )
                    except Exception:
                        pass
                    # Ensure the semaphore and event are released even if thread is stuck
                    if not _ev.is_set():
                        try:
                            semaphore.release()
                        except Exception:
                            pass
                        _ev.set()
                    _running_jobs.discard(_jid)

            watchdog = threading.Thread(target=_watchdog, daemon=True)
            watchdog.start()

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
        _log(f"[engine] Job {job_id} not found in database — marking failed to avoid pending limbo")
        try:
            db.update_job(job_id, status="failed",
                          error="Job record could not be found at execution time (possible restart race condition).")
        except Exception:
            pass
        return

    config = json.loads(job["config"]) if isinstance(job["config"], str) else job["config"]
    url = job["url"]

    _log(f"[engine] Job {job_id} starting for URL: {url}")
    db.update_job(job_id, status="running", started_at=datetime.now().isoformat())

    # Load settings for API keys
    settings = db.get_all_settings()
    # Resolve the extraction model + its API key (provider-aware). The model is
    # configurable per-job, falling back to the saved default, then Claude Sonnet.
    llm_provider = (
        config.get("llm_provider")
        or settings.get("llm_provider")
        or DEFAULT_LLM_PROVIDER
    )
    llm_key = _resolve_llm_key(llm_provider, settings)
    if not llm_key and not llm_provider.lower().startswith("ollama"):
        _log(f"[engine] WARNING: no API key resolved for provider {llm_provider!r}")

    # Build output directory with absolute path to avoid relative path issues
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    output_dir = os.path.join(project_root, "output", job_id)
    os.makedirs(output_dir, exist_ok=True)
    db.update_job(job_id, output_dir=output_dir)

    # Build output backends
    recipients = config.get("recipients", "")
    email_subject = config.get("email_subject") or f"IntelliFetch News Digest: {job['name']}"

    smtp_config = db.get_smtp_config(settings)
    if recipients and not smtp_config.get("smtp_host"):
        _log(f"[engine] Job {job_id}: no SMTP host configured — email will use the "
             f"HTTP API fallback")
    _, _, outputs = create_job_outputs(
        project_root=project_root,
        job_id=job_id,
        title=job["name"],
        email_to=recipients if recipients else None,
        email_subject=email_subject,
        **smtp_config,
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

    # Browser config.
    # --disable-http2: some sites (e.g. businesswire.com) terminate Playwright's
    #   HTTP/2 connection with ERR_HTTP2_PROTOCOL_ERROR; forcing HTTP/1.1 fixes it.
    # --disable-blink-features=AutomationControlled: reduces trivial bot detection.
    # --no-sandbox / --disable-dev-shm-usage: stability in containers (Railway).
    browser_args = [
        "--disable-http2",
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
    # Optional per-job unblocker proxy (BrightData Web Unlocker). Off by default
    # since it is billed per request; enable on jobs whose sites block direct
    # headless access (e.g. businesswire.com).
    proxy_config = None
    if config.get("use_proxy"):
        proxy_config = _resolve_proxy(settings)
        if proxy_config:
            _log(f"[engine] Job {job_id}: routing through unblocker proxy "
                 f"({proxy_config.get('server')})")
        else:
            _log(f"[engine] Job {job_id}: use_proxy set but no proxy credentials "
                 f"configured — proceeding without proxy")

    browser_conf = BrowserConfig(
        headless=True,
        stealth_mode=config.get("stealth", True),
        simulate_human=config.get("simulate_human", True),
        block_images=config.get("block_images", True),
        extra_args=browser_args,
        proxy_config=proxy_config,
    )

    # Current IST time and the rolling 24h window — used in the extraction
    # instruction and the post-filter. The client requirement is news published
    # in the LAST 24 HOURS, not merely "today" (a calendar day would miss late
    # news from the previous evening that is still within 24 hours).
    now_ist = datetime.now(_IST)
    now_str = now_ist.strftime("%B %-d, %Y %H:%M")          # e.g. "March 19, 2026 14:30"
    cutoff_ist = now_ist - timedelta(hours=24)
    cutoff_str = cutoff_ist.strftime("%B %-d, %Y %H:%M")    # 24h earlier

    # Schema fields
    schema_fields = copy.deepcopy(config.get("schema_fields") or {})
    if not schema_fields:
        schema_fields = {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The news headline"},
                "url": {
                    "type": "string",
                    "description": "The full original webpage URL shown for this article",
                },
                "source": {"type": "string", "description": "Publisher name"},
                "category": {"type": "string", "description": "Topic category"},
                "summary": {"type": "string", "description": "One-sentence summary"},
                "time_ago": {"type": "string", "description": "How long ago it was published, e.g. '2 hours ago', '30 minutes ago'"},
                "published_date": {"type": "string", "description": "The publication date AND time if explicitly shown, e.g. 'March 19, 2026 09:00 ET' or '2026-03-19'"},
            },
            "required": ["title"],
        }
    else:
        # Existing auto/custom jobs may predate the Source column. Augment their
        # schema at runtime so scheduled jobs gain URLs without being recreated.
        properties = schema_fields.setdefault("properties", {})
        properties.setdefault(
            "url",
            {
                "type": "string",
                "description": "The full original webpage URL shown for this article",
            },
        )

    # LLM extraction
    default_instruction = (
        f"The current date and time is {now_str} IST (Asia/Kolkata). "
        f"Extract ONLY actual news articles published within the LAST 24 HOURS, "
        f"i.e. on or after {cutoff_str} IST. "
        "DO NOT include older articles. "
        "Ignore ads, promotions, newsletters, events, navigation links, and category labels. "
        "For each article include: title, source, category, summary, time_ago (e.g. '2 hours ago'), "
        "and published_date (the exact date and time shown on the article, if visible). "
        "If an article has no visible publication date or time, include it only if it appears to be recent. "
        "Return a JSON array containing only articles from the last 24 hours."
    )
    # Per-call sizing. NOTE: bigger is NOT better here. Sending ~100k-char chunks
    # and requesting ~16k output tokens makes each Claude call slow enough to hit
    # the request timeout — which both wastes money (timed-out calls are still
    # billed) and drops articles. We use moderate chunks that each complete well
    # within the timeout; the lenient parser still salvages any truncated tail.
    _large_ctx = llm_provider.lower().startswith(("anthropic/", "openai/")) or "claude" in llm_provider.lower()
    content_limit = int(config.get("content_limit") or (40000 if _large_ctx else 12000))
    max_output_tokens = int(config.get("max_output_tokens") or (8000 if _large_ctx else 4000))
    llm_timeout = int(config.get("llm_timeout") or 180)

    extraction_instruction = config.get("extraction_instruction") or default_instruction
    extraction_instruction += (
        "\nFor every extracted article, include a `url` field containing the exact "
        "full URL printed beside that article in the supplied content. Never invent a URL."
    )

    extraction = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider=llm_provider,
            api_token=llm_key,
        ),
        schema=schema_fields,
        extraction_type="schema",
        instruction=extraction_instruction,
        extra_args={"temperature": 0, "max_tokens": max_output_tokens, "timeout": llm_timeout},
        content_length_limit=content_limit,
    )

    run_conf = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction,
    )

    # Deep crawl config
    # Optional adaptive recency stop (hours). When set, the crawler stops
    # scrolling/paginating once it has passed items older than this window,
    # instead of always exhausting the fixed scroll/page caps.
    _recency_raw = config.get("recency_stop_hours")
    recency_stop_hours = float(_recency_raw) if _recency_raw not in (None, "", 0) else None

    deep_conf = DeepCrawlConfig(
        scroll=config.get("scroll", True),
        max_scrolls=int(config.get("max_scrolls", 10)),
        scroll_delay=float(config.get("scroll_delay", 1.0)),
        recency_stop_hours=recency_stop_hours,
        click_load_more=config.get("click_load_more", True),
        # Numbered pagination (opt-in). Needed for listings that paginate rather
        # than infinitely scroll (e.g. PR Newswire, GlobeNewswire) so the full
        # last-24h set is captured, not just page 1.
        paginate=config.get("paginate", False),
        next_page_selector=config.get("next_page_selector", ""),
        max_pages=int(config.get("max_pages", 3)),
        follow_links=config.get("follow_links", True),
        link_selector=config.get("link_selector", "a[href]"),
        link_filter_pattern=config.get("link_filter", ""),
        max_inner_pages=int(config.get("max_inner_pages", 20)),
        # Screenshots are not consumed by any downstream step yet, so default OFF
        # to avoid the extra time + Chromium crash risk for no benefit.
        use_screenshots=config.get("screenshots", False),
        screenshot_dir=os.path.join(output_dir, "screenshots"),
        smart_filter=config.get("smart_filter", True),
    )
    # The destructive LLM noise filter is opt-in (defaults OFF) to preserve recall.
    apply_llm_noise_filter = bool(config.get("llm_noise_filter", False))

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
            extract_stats: Dict[str, Any] = {}
            extracted = await smart_extract(
                all_content,
                run_conf,
                apply_llm_noise_filter=apply_llm_noise_filter,
                stats=extract_stats,
            )
            _log(f"[engine] Job {job_id} step 4/5: smart_extract done")

        crawl_stats = deep_result.get("stats", {}) if isinstance(deep_result, dict) else {}

        # Parse and count articles
        from crawl4ai.output.email_output import EmailOutput as EO
        articles = EO._parse_extracted(extracted)

        # ── Last-24h post-filter (safety net on top of LLM instruction) ──
        if isinstance(articles, list) and articles:
            before_count = len(articles)
            articles = [
                a for a in articles
                if isinstance(a, dict) and is_within_last_24h(a, now_ist)
            ]
            dropped = before_count - len(articles)
            if dropped:
                _log(f"[engine] Job {job_id}: post-filter dropped {dropped} articles older than 24h "
                     f"({len(articles)} remain within last 24h of {now_str})")

            url_candidates = deep_result.get("url_candidates", deep_result.get("article_links", []))
            reconciled_urls = _attach_article_urls(articles, url_candidates)
            with_urls = sum(1 for a in articles if a.get("url"))
            _log(
                f"[engine] Job {job_id}: source URLs present for {with_urls}/{len(articles)} "
                f"articles ({reconciled_urls} restored from crawler links)"
            )

            # Re-serialise the filtered, URL-enriched list so it is what gets
            # stored, emailed, and later consumed by Pharma Intelligence.
            extracted = json.dumps(articles)

        article_count = len(articles) if isinstance(articles, list) else 0

        # ── Drop-funnel telemetry: shows exactly where articles are lost ──
        _log(
            f"[engine] Job {job_id} FUNNEL: "
            f"raw_links={crawl_stats.get('raw_links_found', 0)} → "
            f"article_links={crawl_stats.get('article_links_after_filter', 0)} → "
            f"inner_pages={crawl_stats.get('inner_pages_crawled', 0)} → "
            f"extracted={extract_stats.get('extracted', 0)} → "
            f"deduped={extract_stats.get('deduped', 0)} → "
            f"heuristic_kept={extract_stats.get('heuristic_kept', 0)} → "
            f"llm_kept={extract_stats.get('llm_kept', 0)} → "
            f"within_24h={article_count}"
        )

        # ── Distinguish infrastructure failure from a genuinely quiet news day ──
        # "0 articles" used to be reported as a successful run whether the sites
        # published nothing or every LLM call blew up, so a broken deployment
        # looked identical to a slow news day and went unnoticed for days.
        llm_calls = int(extract_stats.get("llm_calls", 0) or 0)
        llm_errors = int(extract_stats.get("llm_errors", 0) or 0)
        failure_reason = ""
        if llm_calls and llm_errors >= llm_calls:
            failure_reason = (
                f"LLM extraction failed on all {llm_calls} call(s); no articles could be "
                f"parsed. Last error: {extract_stats.get('llm_last_error', 'unknown')}"
            )
        elif content_len == 0:
            listing_err = getattr(listing, "error_message", "") if listing else ""
            failure_reason = (
                "Crawl returned no page content, so there was nothing to extract "
                f"(the site is likely blocking the crawler). {listing_err}".strip()
            )
        if failure_reason:
            _log(f"[engine] Job {job_id} EXTRACTION FAILURE: {failure_reason}")

        _log(f"[engine] Job {job_id} step 5/5: saving {article_count} articles to outputs...")

        # Generate AI summary if requested and articles are available
        if config.get("summarize_with_ai") and article_count > 0 and llm_key:
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
                    model=llm_provider,
                    api_key=llm_key,
                    messages=[
                        {"role": "system", "content": "You are a news analyst. Write clear, concise executive summaries."},
                        {"role": "user", "content": summary_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=200,
                )
                ai_summary = summary_response.choices[0].message.content.strip()
                # Inject the summary into EmailOutput and PDFReportOutput backends
                from crawl4ai.output.pdf_output import PDFReportOutput as PDFR
                for output in outputs:
                    if isinstance(output, EO):
                        output.ai_summary = ai_summary
                    elif isinstance(output, PDFR):
                        output.ai_summary = ai_summary
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

        # A run that produced nothing because extraction broke is a failure, not a
        # completed run with no news — surface it on the dashboard so it gets fixed.
        status = "failed" if (failure_reason and article_count == 0) else "completed"
        update_kwargs: dict = {
            "status": status,
            "finished_at": datetime.now().isoformat(),
            "article_count": article_count,
        }
        if status == "failed":
            update_kwargs["error"] = failure_reason
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
