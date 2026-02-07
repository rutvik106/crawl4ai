"""Anti-bot stealth utilities for Playwright browser contexts.

Applies common fingerprint-masking techniques to make automated
browsers look more like real user sessions.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List

from playwright.async_api import BrowserContext, Page

# Realistic user agents (rotated randomly)
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# JS to mask automation signals
_STEALTH_SCRIPTS: List[str] = [
    # Hide webdriver flag
    """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """,
    # Fake plugins array
    """
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });
    """,
    # Fake languages
    """
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });
    """,
    # Hide Chrome automation indicators
    """
    window.chrome = { runtime: {} };
    """,
    # Patch permissions query
    """
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters);
    """,
]


def get_random_user_agent() -> str:
    """Return a random realistic user agent string."""
    return random.choice(_USER_AGENTS)


async def apply_stealth(context: BrowserContext) -> None:
    """Inject stealth scripts into every new page in the context."""
    combined = "\n".join(_STEALTH_SCRIPTS)
    await context.add_init_script(combined)


async def human_like_delay(min_ms: int = 100, max_ms: int = 500) -> None:
    """Sleep for a random human-like duration."""
    import asyncio
    delay = random.randint(min_ms, max_ms) / 1000.0
    await asyncio.sleep(delay)


async def human_like_scroll(page: Page, scrolls: int = 3) -> None:
    """Simulate human-like scrolling behavior on a page."""
    import asyncio
    for _ in range(scrolls):
        distance = random.randint(200, 600)
        await page.evaluate(f"window.scrollBy(0, {distance})")
        await asyncio.sleep(random.uniform(0.3, 0.8))


async def random_mouse_movement(page: Page, moves: int = 3) -> None:
    """Move the mouse to random positions to appear more human."""
    import asyncio
    viewport = page.viewport_size or {"width": 1920, "height": 1080}
    for _ in range(moves):
        x = random.randint(100, viewport["width"] - 100)
        y = random.randint(100, viewport["height"] - 100)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.1, 0.3))
