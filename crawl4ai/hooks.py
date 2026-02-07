"""Lifecycle hooks for the crawl pipeline.

Hooks are async callables invoked at specific points during a crawl.
Each receives the Playwright ``Page`` and can inspect or mutate it.

Usage::

    async def my_hook(page, context):
        await page.evaluate("document.title")

    config = CrawlerRunConfig(
        hooks={
            "on_page_loaded": my_hook,
            "before_return_html": my_hook,
        }
    )
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from playwright.async_api import Page

# Type alias for hook callables: async def hook(page, context) -> None
HookCallable = Callable[[Page, Dict[str, Any]], Awaitable[None]]

# Recognised hook names and when they fire
HOOK_NAMES = {
    "on_browser_created",    # After browser context is created, before navigation
    "on_page_loaded",        # After page.goto() completes
    "after_js_execution",    # After js_code snippets have run
    "before_return_html",    # Just before HTML is captured and returned
    "on_error",              # When an error occurs during crawl
}


class HookRegistry:
    """Stores and invokes lifecycle hooks."""

    def __init__(self, hooks: Optional[Dict[str, HookCallable]] = None) -> None:
        self._hooks: Dict[str, HookCallable] = {}
        if hooks:
            for name, fn in hooks.items():
                self.register(name, fn)

    def register(self, name: str, fn: HookCallable) -> None:
        if name not in HOOK_NAMES:
            raise ValueError(
                f"Unknown hook '{name}'. Must be one of: {sorted(HOOK_NAMES)}"
            )
        self._hooks[name] = fn

    async def trigger(
        self, name: str, page: Optional[Page], context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Fire a hook if registered. Silently skips if not registered."""
        fn = self._hooks.get(name)
        if fn is None:
            return
        await fn(page, context or {})
