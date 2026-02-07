"""Page interaction utilities — scrolling, lazy loading, pagination."""

from __future__ import annotations

import asyncio
from typing import Optional

from playwright.async_api import Page


async def scroll_to_bottom(
    page: Page,
    max_scrolls: int = 20,
    scroll_delay: float = 1.0,
    scroll_step: int = 800,
) -> int:
    """Scroll the page incrementally to trigger lazy-loaded content.

    Returns the total number of scrolls performed.
    """
    prev_height = 0
    scrolls = 0
    stale_count = 0

    for _ in range(max_scrolls):
        await page.evaluate(f"window.scrollBy(0, {scroll_step})")
        await asyncio.sleep(scroll_delay)
        scrolls += 1

        cur_height = await page.evaluate("document.body.scrollHeight")
        if cur_height == prev_height:
            stale_count += 1
            if stale_count >= 3:
                break  # No new content after 3 consecutive scrolls
        else:
            stale_count = 0
        prev_height = cur_height

    return scrolls


async def click_load_more(
    page: Page,
    selector: str = "",
    max_clicks: int = 10,
    click_delay: float = 2.0,
) -> int:
    """Click a "Load More" / "Show More" button repeatedly.

    If no selector is provided, tries common selectors automatically.
    Returns the number of successful clicks.
    """
    common_selectors = [
        selector,
        "button:has-text('Load More')",
        "button:has-text('Show More')",
        "button:has-text('View More')",
        "a:has-text('Load More')",
        "a:has-text('Show More')",
        "[class*='load-more']",
        "[class*='loadMore']",
        "[class*='show-more']",
        "[data-action='load-more']",
    ]

    # Filter empty and deduplicate
    selectors = list(dict.fromkeys(s for s in common_selectors if s))

    clicks = 0
    for _ in range(max_clicks):
        clicked = False
        for sel in selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(click_delay)
                    clicks += 1
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            break

    return clicks


async def handle_pagination(
    page: Page,
    next_selector: str = "",
    max_pages: int = 5,
    page_delay: float = 2.0,
) -> list:
    """Navigate through paginated pages, collecting HTML from each.

    Returns a list of HTML strings (one per page).
    """
    common_next_selectors = [
        next_selector,
        "a:has-text('Next')",
        "a:has-text('›')",
        "a:has-text('»')",
        "[class*='next']",
        "[aria-label='Next']",
        "li.next a",
        ".pagination a:last-child",
    ]
    selectors = list(dict.fromkeys(s for s in common_next_selectors if s))

    pages_html = [await page.content()]

    for _ in range(max_pages - 1):
        clicked = False
        for sel in selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(page_delay)
                    await page.wait_for_load_state("domcontentloaded")
                    pages_html.append(await page.content())
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            break

    return pages_html


async def extract_links(
    page: Page,
    selector: str = "a[href]",
    base_url: str = "",
    filter_pattern: Optional[str] = None,
) -> list:
    """Extract all links matching a selector from the current page.

    Returns a list of dicts with 'url' and 'text' keys.
    """
    import re
    from urllib.parse import urljoin

    links = await page.evaluate(f"""
        () => {{
            const els = document.querySelectorAll('{selector}');
            return Array.from(els).map(a => ({{
                url: a.href,
                text: (a.textContent || '').trim().substring(0, 200)
            }}));
        }}
    """)

    # Resolve relative URLs
    if base_url:
        for link in links:
            if link["url"] and not link["url"].startswith("http"):
                link["url"] = urljoin(base_url, link["url"])

    # Filter by pattern
    if filter_pattern:
        pat = re.compile(filter_pattern)
        links = [l for l in links if pat.search(l["url"])]

    # Deduplicate by URL
    seen = set()
    unique = []
    for link in links:
        if link["url"] not in seen:
            seen.add(link["url"])
            unique.append(link)

    return unique


async def take_full_screenshot(
    page: Page,
    path: str = "",
    full_page: bool = True,
) -> bytes:
    """Take a screenshot of the page. Returns PNG bytes."""
    kwargs = {"full_page": full_page, "type": "png"}
    if path:
        kwargs["path"] = path
    return await page.screenshot(**kwargs)
