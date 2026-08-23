"""Deep crawler — scroll, collect links, crawl inner pages, smart extraction.

Usage::

    from crawl4ai.deep_crawler import DeepCrawlConfig, deep_crawl

    config = DeepCrawlConfig(
        scroll=True,
        max_scrolls=15,
        follow_links=True,
        link_selector="a[href*='/news/']",
        max_inner_pages=10,
        use_screenshots=True,
    )
    results = await deep_crawl(crawler, url, config, run_conf)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .async_webcrawler import AsyncWebCrawler
    from .crawler_run_config import CrawlerRunConfig


@dataclass
class DeepCrawlConfig:
    """Configuration for deep crawling behavior."""

    # --- Scrolling ---
    scroll: bool = True
    max_scrolls: int = 15
    scroll_delay: float = 1.0
    # Optional adaptive stop: stop scrolling/paginating once items are older than
    # this many hours (relative-time heuristic). None = scroll up to max_scrolls.
    recency_stop_hours: Optional[float] = None

    # --- Load More ---
    click_load_more: bool = True
    load_more_selector: str = ""
    max_load_more_clicks: int = 5

    # --- Pagination ---
    paginate: bool = False
    next_page_selector: str = ""
    max_pages: int = 3

    # --- Follow links to inner pages ---
    follow_links: bool = True
    link_selector: str = "a[href]"
    link_filter_pattern: Optional[str] = None
    max_inner_pages: int = 20
    inner_page_delay: float = 1.0
    inner_page_timeout: float = 60.0  # seconds per inner page crawl

    # --- Screenshots for vision LLM ---
    use_screenshots: bool = False
    screenshot_dir: str = ""

    # --- Smart filtering ---
    smart_filter: bool = True
    filter_instruction: str = (
        "From the following content, identify ONLY actual news articles. "
        "Remove any ads, promotions, newsletters, navigation items, or noise. "
        "Return a JSON array of the real news articles with title, source, category, and summary."
    )


async def deep_crawl(
    crawler: "AsyncWebCrawler",
    url: str,
    deep_config: DeepCrawlConfig,
    run_conf: "CrawlerRunConfig",
) -> Dict[str, Any]:
    """Perform a deep crawl: scroll, collect links, crawl inner pages, aggregate.

    Returns a dict with:
        - listing_result: CrawlResult from the main listing page
        - inner_results: list of CrawlResults from inner pages
        - all_content: aggregated markdown from all pages
        - screenshots: list of screenshot paths (if enabled)
        - article_links: list of discovered article links
    """
    from .models import CrawlResult, MarkdownResult
    from .page_actions import (
        scroll_to_bottom,
        click_load_more,
        click_next_page,
        extract_links,
        take_full_screenshot,
    )

    result: Dict[str, Any] = {
        "listing_result": None,
        "inner_results": [],
        "all_content": "",
        "screenshots": [],
        "article_links": [],
        # Per-stage funnel so we can see exactly where articles are lost.
        "stats": {
            "raw_links_found": 0,
            "article_links_after_filter": 0,
            "inner_pages_crawled": 0,
        },
    }

    # ---- Phase 1: Crawl the listing page with scrolling ----
    # Use a session so we keep the page open for scrolling
    session_id = f"deep_crawl_{id(deep_config)}"
    listing_conf = run_conf.clone(
        session_id=session_id,
        delay_before_return_html=1.0,
        extraction_strategy=None,  # Don't extract yet — we collect raw content first
    )
    listing_conf.output = None  # Don't dispatch intermediate results to output backends

    listing_result = await crawler.arun(url=url, config=listing_conf)

    if not listing_result.success:
        result["listing_result"] = listing_result
        return result

    # Get the page from the session for interactive actions
    page = crawler._sessions.get(session_id)
    if not page:
        result["listing_result"] = listing_result
        return result

    # ---- Phase 2: Scroll to load lazy content ----
    if deep_config.scroll:
        scrolls = await scroll_to_bottom(
            page,
            max_scrolls=deep_config.max_scrolls,
            scroll_delay=deep_config.scroll_delay,
            stop_when_older_than_hours=deep_config.recency_stop_hours,
        )
        print(f"  Scrolled {scrolls} times", flush=True)

    # ---- Phase 3: Click "Load More" buttons ----
    if deep_config.click_load_more:
        clicks = await click_load_more(
            page,
            selector=deep_config.load_more_selector,
            max_clicks=deep_config.max_load_more_clicks,
        )
        if clicks:
            print(f"  Clicked 'Load More' {clicks} times", flush=True)

    # ---- Phase 4: Re-capture HTML after scrolling ----
    html_after_scroll = await page.content()
    md_gen = run_conf.markdown_generator or crawler._default_md_generator
    listing_md = md_gen.convert(html_after_scroll)
    listing_result.html = html_after_scroll
    listing_result.markdown = listing_md
    result["listing_result"] = listing_result

    all_content_parts = [f"=== LISTING PAGE: {url} ===\n{listing_md.raw_markdown}\n"]

    # ---- Phase 5: Extract article links (across paginated pages) ----
    article_links = []
    if deep_config.follow_links:
        raw_links = await extract_links(
            page,
            selector=deep_config.link_selector,
            base_url=url,
            filter_pattern=deep_config.link_filter_pattern,
        )

        # ---- Phase 5b: Walk numbered pagination (opt-in) ----
        # Sites like PR Newswire / GlobeNewswire paginate their listings rather
        # than infinitely scrolling, so without this the brief would only ever
        # see the first page (and miss within-24h items further back).
        if deep_config.paginate:
            pages_walked = 1
            while pages_walked < deep_config.max_pages:
                advanced = await click_next_page(
                    page,
                    next_selector=deep_config.next_page_selector,
                )
                if not advanced:
                    break
                pages_walked += 1
                if deep_config.scroll:
                    await scroll_to_bottom(
                        page,
                        max_scrolls=deep_config.max_scrolls,
                        scroll_delay=deep_config.scroll_delay,
                        stop_when_older_than_hours=deep_config.recency_stop_hours,
                    )
                page_html = await page.content()
                page_md = md_gen.convert(page_html)
                all_content_parts.append(
                    f"\n=== LISTING PAGE {pages_walked}: {page.url} ===\n"
                    f"{page_md.raw_markdown}\n"
                )
                raw_links += await extract_links(
                    page,
                    selector=deep_config.link_selector,
                    base_url=url,
                    filter_pattern=deep_config.link_filter_pattern,
                )
                # Adaptive stop: if this page's items are already older than the
                # recency window, deeper pages are older too — stop paginating.
                if deep_config.recency_stop_hours:
                    from .page_actions import page_oldest_age_hours
                    oldest = await page_oldest_age_hours(page)
                    if oldest is not None and oldest > deep_config.recency_stop_hours:
                        print(
                            f"  Stopping pagination at page {pages_walked}: items older "
                            f"than {deep_config.recency_stop_hours}h",
                            flush=True,
                        )
                        break
            print(f"  Paginated through {pages_walked} listing page(s)", flush=True)

        # De-duplicate links by URL (the same item may appear on multiple pages).
        _seen_urls = set()
        article_links = []
        for _l in raw_links:
            if _l["url"] not in _seen_urls:
                _seen_urls.add(_l["url"])
                article_links.append(_l)

        # Filter out non-article links (homepage, category pages, externals, anchors)
        from urllib.parse import urlparse
        base_parsed = urlparse(url)
        base_domain = base_parsed.netloc
        base_path = base_parsed.path.rstrip("/")

        # Common non-article path patterns to skip. Expanded to exclude the
        # marketing / account / category-landing pages that newswire sites put in
        # their header/footer (these were being followed instead of real releases,
        # bloating content and burning LLM budget on junk).
        _SKIP_PATTERNS = re.compile(
            r"^/(#|$)|/pre-markets|/markets|/login|/signup|/sign-?in|/register"
            r"|/subscribe|/newsletter|/video|/podcast|/about|/contact|/privacy"
            r"|/terms|/sitemap|/author|/tag/|/category/|/search|/account"
            r"|/resources?|/products?|/services?|/solutions?|/pricing|/advertis"
            r"|/amplify|/distribution|/multimedia|/all-products|latest-news-topics"
            r"|-latest-news|/help|/careers|/support",
            re.IGNORECASE,
        )

        # Positive signal that a URL is an actual article/press release rather
        # than a section/landing page: ends in .html, has a dated path, or has a
        # long numeric id. Used as a *preference* (with fallback) so it helps
        # newswire-style sites without breaking sites that don't use these forms.
        _ARTICLE_HINT_RE = re.compile(r"\.html?($|\?)|/20\d\d/\d|/\d{6,}", re.IGNORECASE)

        def _is_article_link(link: dict) -> bool:
            parsed = urlparse(link["url"])
            # Must be same domain
            if parsed.netloc != base_domain:
                return False
            # Skip anchor-only links
            path = parsed.path.rstrip("/")
            if not path or path == base_path:
                return False
            # Skip links with only a fragment
            if link["url"].startswith(url.rstrip("/") + "#"):
                return False
            # Skip only truly tiny nav links. The old threshold of 15 chars cut
            # many legitimate short headlines, so we relax it.
            if len(link["text"].strip()) < 6:
                return False
            # Skip common non-article paths
            if _SKIP_PATTERNS.search(path):
                return False
            # Require at least one real path segment. The old rule (>=2 slashes)
            # discarded valid shallow article URLs like /news/12345.
            if path.count("/") < 1:
                return False
            return True

        result["stats"]["raw_links_found"] = len(raw_links)
        filtered_links = [l for l in article_links if _is_article_link(l)]
        # Prefer article-shaped URLs when any exist; otherwise fall back to the
        # generic filtered set so non-standard sites still work.
        hinted = [l for l in filtered_links
                  if _ARTICLE_HINT_RE.search(urlparse(l["url"]).path)]
        chosen = hinted if hinted else filtered_links
        # Preserve every discovered headline→URL pair for deterministic source
        # reconciliation after LLM extraction. Only the capped subset below is
        # fetched in full, but listing-only articles can still retain their URL.
        result["url_candidates"] = chosen
        article_links = chosen[:deep_config.max_inner_pages]
        result["article_links"] = article_links
        result["stats"]["article_links_after_filter"] = len(article_links)
        print(f"  Found {len(article_links)} article links to follow "
              f"(from {len(raw_links)} raw links)", flush=True)

    # ---- Phase 6: Take screenshot (optional, after content is captured) ----
    screenshots = []
    if deep_config.use_screenshots:
        ss_dir = deep_config.screenshot_dir or "/tmp/crawl4ai_screenshots"
        os.makedirs(ss_dir, exist_ok=True)
        ss_path = os.path.join(ss_dir, "listing_page.png")
        try:
            await take_full_screenshot(page, path=ss_path)
            screenshots.append(ss_path)
            print(f"  Screenshot saved: {ss_path}", flush=True)
        except Exception as e:
            print(f"  Screenshot failed (non-fatal): {e}", flush=True)
            # Screenshot may have crashed Chromium — reset browser so
            # inner page crawls can relaunch it via _ensure_browser()
            try:
                if crawler._browser:
                    await crawler._browser.close()
            except Exception:
                pass
            crawler._browser = None
            crawler._sessions.clear()
            print("  Browser reset after crash, will relaunch for inner pages", flush=True)

    # Kill the listing session (may fail if browser crashed)
    try:
        await crawler.kill_session(session_id)
    except Exception:
        pass

    # ---- Phase 7: Crawl inner pages ----
    if article_links:
        inner_conf = run_conf.clone(
            delay_before_return_html=2.0,
            extraction_strategy=None,  # Raw content only
        )
        inner_conf.output = None  # Don't dispatch intermediate results

        inner_results = []
        for i, link in enumerate(article_links):
            print(f"  [{i+1}/{len(article_links)}] Crawling: {link['url'][:80]}", flush=True)
            try:
                inner_result = await asyncio.wait_for(
                    crawler.arun(url=link["url"], config=inner_conf),
                    timeout=deep_config.inner_page_timeout,
                )
                if inner_result.success:
                    inner_results.append(inner_result)
                    all_content_parts.append(
                        f"\n=== ARTICLE: {link['text'][:100]} ===\n"
                        f"URL: {link['url']}\n"
                        f"{inner_result.markdown.raw_markdown[:3000]}\n"
                    )

                    # Screenshot inner pages too
                    if deep_config.use_screenshots:
                        ss_path = os.path.join(ss_dir, f"article_{i+1}.png")
                        # Can't screenshot already-closed pages, skip
                        screenshots.append(ss_path)
                else:
                    print(f"    Failed: {inner_result.error_message[:100] if inner_result.error_message else 'unknown'}", flush=True)
            except asyncio.TimeoutError:
                print(f"    TIMEOUT after {deep_config.inner_page_timeout}s, skipping", flush=True)
            except Exception as e:
                print(f"    Error: {e}", flush=True)

            await asyncio.sleep(deep_config.inner_page_delay)

        result["inner_results"] = inner_results
        result["stats"]["inner_pages_crawled"] = len(inner_results)
        print(f"  Crawled {len(inner_results)} inner pages successfully", flush=True)

    # ---- Phase 8: Aggregate all content ----
    result["all_content"] = "\n".join(all_content_parts)
    result["screenshots"] = screenshots

    return result


async def smart_extract(
    all_content: str,
    run_conf: "CrawlerRunConfig",
    instruction: str = "",
    screenshots: Optional[List[str]] = None,
    apply_llm_noise_filter: bool = False,
    stats: Optional[Dict[str, Any]] = None,
) -> str:
    """Run LLM extraction on aggregated content with smart filtering.

    Pipeline:
      1. Extract articles from content (chunked if too large)
      2. Deduplicate by title
      3. Heuristic noise filter (remove nav items, category labels, promos)
      4. (Optional) LLM second-pass filter — OFF by default because it routinely
         deletes legitimate headlines it misjudges as "noise", which dropped real
         news. Enable only when precision matters more than recall.
    """
    from .extraction.llm_extraction import LLMExtractionStrategy

    strategy = run_conf.extraction_strategy
    if not isinstance(strategy, LLMExtractionStrategy):
        print("[smart_extract] strategy is not LLMExtractionStrategy, returning empty")
        return ""

    print(f"[smart_extract] content length: {len(all_content)} chars")

    if not all_content or not all_content.strip():
        print("[smart_extract] Empty content, skipping LLM extraction")
        return "[]"

    # Override instruction for smart filtering
    if instruction:
        original_instruction = strategy.instruction
        strategy.instruction = instruction

    # Check if content fits in context window
    content_limit = strategy.content_length_limit or 12000

    # Count LLM calls vs. failures so the caller can tell "the site had no news"
    # apart from "every LLM call errored" — the two are indistinguishable from an
    # empty result set, and conflating them hid a broken deployment for days.
    llm_calls = 0
    llm_errors = 0
    last_error = ""

    if len(all_content) <= content_limit:
        # Fits — extract directly
        print(f"[smart_extract] Content fits ({len(all_content)} <= {content_limit}), extracting directly...")
        llm_calls = 1
        try:
            result = await strategy.aextract("aggregated", all_content)
            print(f"[smart_extract] LLM returned {len(result) if result else 0} chars")
            print(f"[smart_extract] LLM preview: {str(result)[:200]}")
        except Exception as e:
            print(f"[smart_extract] LLM extract ERROR: {e}")
            llm_errors, last_error = 1, str(e)
            result = "[]"
        all_extracted = _parse_articles_lenient(result)
        if not all_extracted:
            print("[smart_extract] No articles parsed from result (empty or unrecoverable)")
    else:
        # Content too large — chunk and merge
        chunks = _chunk_content(all_content, chunk_size=content_limit)
        all_extracted = []

        print(f"[smart_extract] Content too large ({len(all_content)} chars), splitting into {len(chunks)} chunks")

        for i, chunk in enumerate(chunks):
            print(f"[smart_extract] Extracting chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")
            llm_calls += 1
            try:
                extracted = await strategy.aextract("aggregated", chunk)
                print(f"[smart_extract]   Chunk {i+1} returned {len(extracted) if extracted else 0} chars")
            except Exception as e:
                print(f"[smart_extract]   Chunk {i+1} ERROR: {e}")
                llm_errors, last_error = llm_errors + 1, str(e)
                continue
            items = _parse_articles_lenient(extracted)
            all_extracted.extend(items)
            print(f"[smart_extract]   Chunk {i+1}: {len(items)} items")

    if instruction:
        strategy.instruction = original_instruction

    print(f"[smart_extract] Total extracted: {len(all_extracted)} items")

    # ---- Step 2: Deduplicate by title ----
    seen_titles = set()
    unique = []
    for item in all_extracted:
        title = item.get("title", "").strip().lower()
        if title and title not in seen_titles:
            seen_titles.add(title)
            unique.append(item)

    print(f"  After dedup: {len(unique)} articles")

    # ---- Step 3: Heuristic noise filter ----
    cleaned = _heuristic_filter(unique)
    heuristic_kept = len(cleaned)
    print(f"  After heuristic filter: {heuristic_kept} articles (removed {len(unique) - heuristic_kept} noise items)")

    # ---- Step 4: LLM second-pass filter (opt-in) ----
    if apply_llm_noise_filter and cleaned and isinstance(strategy, LLMExtractionStrategy):
        cleaned = await _llm_noise_filter(cleaned, strategy)
        print(f"  After LLM noise filter: {len(cleaned)} articles")
    elif not apply_llm_noise_filter:
        print("  LLM noise filter disabled (recall-preserving default)")

    if stats is not None:
        stats["extracted"] = len(all_extracted)
        stats["deduped"] = len(unique)
        stats["heuristic_kept"] = heuristic_kept
        stats["llm_kept"] = len(cleaned)
        stats["llm_calls"] = llm_calls
        stats["llm_errors"] = llm_errors
        if last_error:
            stats["llm_last_error"] = last_error

    return json.dumps(cleaned, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------ #
# Noise filtering
# ------------------------------------------------------------------ #

# Navigation / category patterns that are NOT real news
_NOISE_PATTERNS = [
    r"^regulatory\s+update$",
    r"^drug\s+approvals?\s*(&|and)\s*launches?$",
    r"^financial\s+performance$",
    r"^policy\s*(&|and)\s*regulations?$",
    r"^mergers?\s*(&|and)\s*acquisitions?$",
    r"^pharma\s*(tech|industry)?$",
    r"^follow\s+us\b",
    r"^subscribe\b",
    r"^newsletter\b",
    r"^explore\s+and\s+subscribe",
    r"^get\s+updates?\b",
    r"^download\s+app\b",
    r"^get\s+app\b",
    r"^sign\s+up\b",
    r"^log\s*in\b",
    r"^advertise\b",
    r"^contact\s+us\b",
    r"^about\s+us\b",
    r"^read\s+more\b",
    r"^view\s+(all|more)\b",
    r"^trending\b",
    r"^exclusive$",
    r"^sponsored\b",
    r"^brand\s+solutions?\b",
    r"^et\s*pharma\s+newsletter\b",
    r"^re-?pharma\s+awards\b",
    r"^india\s+inc\s+on\s+the\s+move\b",
]

_NOISE_RE = [re.compile(p, re.IGNORECASE) for p in _NOISE_PATTERNS]


def _heuristic_filter(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove obvious noise: nav items, category labels, promos, short titles."""
    filtered = []
    for article in articles:
        title = article.get("title", "").strip()

        # Skip empty / very short titles (likely nav items). Relaxed from 8 to 5
        # so short-but-real headlines are not dropped.
        if len(title) < 5:
            continue

        # Skip if title matches a known noise pattern
        if any(pat.search(title) for pat in _NOISE_RE):
            continue

        # Single-word titles are usually category labels — but only treat them as
        # noise when they are also short, so we don't drop a real one-word headline.
        if " " not in title and len(title) < 12:
            continue

        filtered.append(article)

    return filtered


async def _llm_noise_filter(
    articles: List[Dict[str, Any]],
    strategy: Any,
) -> List[Dict[str, Any]]:
    """Use LLM to review extracted articles and remove non-news items.

    Sends a compact list of titles to the LLM and asks it to classify
    each as real news or noise.
    """
    if len(articles) <= 3:
        return articles

    # Build a compact list of titles for review
    title_list = "\n".join(
        f"{i+1}. {a.get('title', 'N/A')}"
        for i, a in enumerate(articles)
    )

    review_prompt = (
        "Below is a numbered list of items extracted from a news website. "
        "Some are REAL NEWS ARTICLES, others are noise (navigation labels, "
        "category headers, newsletter promos, event announcements, ads, "
        "awards listings, social media CTAs, or section titles).\n\n"
        "Return ONLY a JSON array of the numbers (integers) that are REAL NEWS ARTICLES. "
        "Exclude anything that is not an actual news story.\n\n"
        f"Items:\n{title_list}\n\n"
        "Response format: [1, 3, 5, 7, ...]"
    )

    original_instruction = strategy.instruction
    original_schema = strategy.schema
    strategy.instruction = review_prompt
    strategy.schema = None  # Free-form response

    try:
        response = await strategy.aextract("filter", review_prompt)

        # Parse the response — expect a JSON array of integers
        response = response.strip()
        # Try to find a JSON array in the response
        match = re.search(r"\[[\d,\s]+\]", response)
        if match:
            keep_indices = json.loads(match.group())
            # Convert to 0-indexed
            keep_set = {int(i) - 1 for i in keep_indices if isinstance(i, (int, float))}
            filtered = [a for idx, a in enumerate(articles) if idx in keep_set]
            if filtered:
                return filtered
    except Exception as e:
        print(f"  LLM noise filter error: {e}")
    finally:
        strategy.instruction = original_instruction
        strategy.schema = original_schema

    return articles  # Fallback: return unfiltered


def _parse_articles_lenient(raw: str) -> List[Dict[str, Any]]:
    """Parse an LLM JSON array of articles, salvaging as much as possible.

    LLM output is frequently truncated mid-array (e.g. hitting max_tokens) or has
    minor syntax issues. A strict ``json.loads`` returns nothing in that case, so
    we would drop *every* article in the batch — a major source of "missing news".
    Strategy: strict parse first; if that fails, recover every complete top-level
    ``{...}`` object via brace/string-aware scanning (so a truncated tail only
    loses the final, incomplete object instead of the whole batch).
    """
    if not raw or not raw.strip():
        return []

    # 1) Strict parse (handles the normal, well-formed case).
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        if isinstance(data, dict):
            return [data]
    except (json.JSONDecodeError, TypeError):
        pass

    # 2) Salvage complete top-level objects, ignoring braces inside strings.
    objects: List[Dict[str, Any]] = []
    depth = 0
    start: Optional[int] = None
    in_str = False
    esc = False
    for i, ch in enumerate(raw):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        obj = json.loads(raw[start : i + 1])
                        if isinstance(obj, dict):
                            objects.append(obj)
                    except json.JSONDecodeError:
                        pass
                    start = None
    return objects


def _chunk_content(text: str, chunk_size: int = 10000) -> List[str]:
    """Split text into chunks at paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > chunk_size and current:
            chunks.append(current)
            current = para
        else:
            current = current + "\n\n" + para if current else para

    if current:
        chunks.append(current)

    return chunks
