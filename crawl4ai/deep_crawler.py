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
    max_inner_pages: int = 10
    inner_page_delay: float = 1.0

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
        handle_pagination,
        extract_links,
        take_full_screenshot,
    )

    result: Dict[str, Any] = {
        "listing_result": None,
        "inner_results": [],
        "all_content": "",
        "screenshots": [],
        "article_links": [],
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
        )
        print(f"  Scrolled {scrolls} times")

    # ---- Phase 3: Click "Load More" buttons ----
    if deep_config.click_load_more:
        clicks = await click_load_more(
            page,
            selector=deep_config.load_more_selector,
            max_clicks=deep_config.max_load_more_clicks,
        )
        if clicks:
            print(f"  Clicked 'Load More' {clicks} times")

    # ---- Phase 4: Take screenshot of fully loaded page ----
    screenshots = []
    if deep_config.use_screenshots:
        ss_dir = deep_config.screenshot_dir or "/tmp/crawl4ai_screenshots"
        os.makedirs(ss_dir, exist_ok=True)
        ss_path = os.path.join(ss_dir, "listing_page.png")
        await take_full_screenshot(page, path=ss_path)
        screenshots.append(ss_path)
        print(f"  Screenshot saved: {ss_path}")

    # ---- Phase 5: Re-capture HTML after scrolling ----
    html_after_scroll = await page.content()
    md_gen = run_conf.markdown_generator or crawler._default_md_generator
    listing_md = md_gen.convert(html_after_scroll)
    listing_result.html = html_after_scroll
    listing_result.markdown = listing_md
    result["listing_result"] = listing_result

    all_content_parts = [f"=== LISTING PAGE: {url} ===\n{listing_md.raw_markdown}\n"]

    # ---- Phase 6: Extract article links ----
    article_links = []
    if deep_config.follow_links:
        article_links = await extract_links(
            page,
            selector=deep_config.link_selector,
            base_url=url,
            filter_pattern=deep_config.link_filter_pattern,
        )
        # Filter out non-article links (homepage, category pages, externals)
        from urllib.parse import urlparse
        base_domain = urlparse(url).netloc
        article_links = [
            l for l in article_links
            if urlparse(l["url"]).netloc == base_domain
            and len(l["text"]) > 10  # Skip tiny nav links
            and l["url"] != url  # Skip self-link
        ]
        article_links = article_links[:deep_config.max_inner_pages]
        result["article_links"] = article_links
        print(f"  Found {len(article_links)} article links to follow")

    # Kill the listing session
    await crawler.kill_session(session_id)

    # ---- Phase 7: Crawl inner pages ----
    if article_links:
        inner_conf = run_conf.clone(
            delay_before_return_html=2.0,
            extraction_strategy=None,  # Raw content only
        )
        inner_conf.output = None  # Don't dispatch intermediate results

        inner_results = []
        for i, link in enumerate(article_links):
            print(f"  [{i+1}/{len(article_links)}] Crawling: {link['url'][:80]}")
            try:
                inner_result = await crawler.arun(url=link["url"], config=inner_conf)
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
            except Exception as e:
                print(f"    Error: {e}")

            await asyncio.sleep(deep_config.inner_page_delay)

        result["inner_results"] = inner_results
        print(f"  Crawled {len(inner_results)} inner pages successfully")

    # ---- Phase 8: Aggregate all content ----
    result["all_content"] = "\n".join(all_content_parts)
    result["screenshots"] = screenshots

    return result


async def smart_extract(
    all_content: str,
    run_conf: "CrawlerRunConfig",
    instruction: str = "",
    screenshots: Optional[List[str]] = None,
) -> str:
    """Run LLM extraction on aggregated content with smart filtering.

    Pipeline:
      1. Extract articles from content (chunked if too large)
      2. Deduplicate by title
      3. Heuristic noise filter (remove nav items, category labels, promos)
      4. LLM second-pass filter (review remaining items for real news)
    """
    from .extraction.llm_extraction import LLMExtractionStrategy

    strategy = run_conf.extraction_strategy
    if not isinstance(strategy, LLMExtractionStrategy):
        return ""

    # Override instruction for smart filtering
    if instruction:
        original_instruction = strategy.instruction
        strategy.instruction = instruction

    # Check if content fits in context window
    content_limit = strategy.content_length_limit or 12000

    if len(all_content) <= content_limit:
        # Fits — extract directly
        result = strategy.extract("aggregated", all_content)
        try:
            all_extracted = json.loads(result)
            if not isinstance(all_extracted, list):
                all_extracted = []
        except (json.JSONDecodeError, TypeError):
            all_extracted = []
    else:
        # Content too large — chunk and merge
        chunks = _chunk_content(all_content, chunk_size=content_limit)
        all_extracted = []

        print(f"  Content too large ({len(all_content)} chars), splitting into {len(chunks)} chunks")

        for i, chunk in enumerate(chunks):
            print(f"  Extracting chunk {i+1}/{len(chunks)}...")
            extracted = strategy.extract("aggregated", chunk)
            try:
                items = json.loads(extracted)
                if isinstance(items, list):
                    all_extracted.extend(items)
            except (json.JSONDecodeError, TypeError):
                pass

    if instruction:
        strategy.instruction = original_instruction

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
    print(f"  After heuristic filter: {len(cleaned)} articles (removed {len(unique) - len(cleaned)} noise items)")

    # ---- Step 4: LLM second-pass filter ----
    if cleaned and isinstance(strategy, LLMExtractionStrategy):
        cleaned = await _llm_noise_filter(cleaned, strategy)
        print(f"  After LLM noise filter: {len(cleaned)} articles")

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

        # Skip very short titles (likely nav items)
        if len(title) < 8:
            continue

        # Skip if title matches a known noise pattern
        if any(pat.search(title) for pat in _NOISE_RE):
            continue

        # Skip if title has no spaces (single word = likely a category)
        if " " not in title:
            continue

        # Skip if summary is empty AND title looks like a section header
        summary = article.get("summary", "").strip()
        if not summary and len(title.split()) <= 3:
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
        response = strategy.extract("filter", review_prompt)

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
