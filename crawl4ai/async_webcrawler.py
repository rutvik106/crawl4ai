"""Core async web crawler powered by Playwright."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Route

from .browser_config import BrowserConfig
from .cache_mode import CacheMode
from .crawler_run_config import CrawlerRunConfig
from .hooks import HookRegistry
from .markdown_generation_strategy import DefaultMarkdownGenerator
from .models import CrawlResult, MarkdownResult


class AsyncWebCrawler:
    """Asynchronous web crawler with headless browser support.

    Usage::

        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun("https://example.com")
            print(result.markdown)
    """

    def __init__(self, config: Optional[BrowserConfig] = None) -> None:
        self.config = config or BrowserConfig()
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._sessions: Dict[str, Page] = {}
        self._default_md_generator = DefaultMarkdownGenerator()

    # ------------------------------------------------------------------ #
    # Context manager
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> "AsyncWebCrawler":
        # Browser is launched lazily on first real page request
        return self

    async def _ensure_browser(self) -> None:
        """Lazily start Playwright and launch the browser on first need."""
        if self._browser is not None:
            return

        self._playwright = await async_playwright().start()
        launch_kwargs: Dict[str, Any] = {
            "headless": self.config.headless,
        }
        if self.config.proxy:
            launch_kwargs["proxy"] = {"server": self.config.proxy}
        elif self.config.proxy_config:
            launch_kwargs["proxy"] = self.config.proxy_config
        if self.config.extra_args:
            launch_kwargs["args"] = self.config.extra_args

        launcher = getattr(self._playwright, self.config.browser_type, self._playwright.chromium)
        self._browser = await launcher.launch(**launch_kwargs)

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # Close all tracked sessions
        for page in self._sessions.values():
            try:
                await page.close()
            except Exception:
                pass
        self._sessions.clear()

        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # ------------------------------------------------------------------ #
    # Single-URL crawl
    # ------------------------------------------------------------------ #

    async def arun(
        self,
        url: str = "",
        config: Optional[CrawlerRunConfig] = None,
        **kwargs: Any,
    ) -> CrawlResult:
        """Crawl a single URL and return a ``CrawlResult``."""
        if not url and "url" in kwargs:
            url = kwargs.pop("url")

        run_conf = config or CrawlerRunConfig()
        result = CrawlResult(url=url)

        try:
            html = await self._fetch_html(url, run_conf)
            result.html = html
            result.success = True

            # Markdown generation
            md_gen = run_conf.markdown_generator or self._default_md_generator
            result.markdown = md_gen.convert(html)

            # Extraction strategy
            if run_conf.extraction_strategy is not None:
                # LLM strategies get markdown (compact); CSS strategies get HTML
                from .extraction.llm_extraction import LLMExtractionStrategy
                content_for_extraction = (
                    result.markdown.raw_markdown
                    if isinstance(run_conf.extraction_strategy, LLMExtractionStrategy)
                    else html
                )
                extracted = await self._run_extraction(
                    run_conf.extraction_strategy, url, content_for_extraction
                )
                result.extracted_content = extracted

        except Exception as exc:
            result.success = False
            result.error_message = str(exc)

        # Dispatch to output backends
        if run_conf.output:
            from .output.base import OutputManager
            manager = OutputManager(run_conf.output)
            manager.save(result)

        return result

    # ------------------------------------------------------------------ #
    # Multi-URL crawl
    # ------------------------------------------------------------------ #

    async def arun_many(
        self,
        urls: List[str],
        config: Optional[CrawlerRunConfig] = None,
        **kwargs: Any,
    ) -> Union[List[CrawlResult], "AsyncResultStream"]:
        """Crawl multiple URLs concurrently.

        Returns:
            If ``config.stream`` is True, returns an ``AsyncResultStream``
            that yields results as they complete.
            Otherwise, returns a list of ``CrawlResult``.
        """
        run_conf = config or CrawlerRunConfig()

        if run_conf.stream:
            return AsyncResultStream(self, urls, run_conf)

        # Batch mode – run all concurrently with a semaphore
        sem = asyncio.Semaphore(10)

        async def _bounded(u: str) -> CrawlResult:
            async with sem:
                return await self.arun(url=u, config=run_conf)

        return await asyncio.gather(*[_bounded(u) for u in urls])

    # ------------------------------------------------------------------ #
    # Session management
    # ------------------------------------------------------------------ #

    async def kill_session(self, session_id: str) -> None:
        """Close and discard a named browser session/page."""
        page = self._sessions.pop(session_id, None)
        if page:
            try:
                await page.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    async def _get_page(self, run_conf: CrawlerRunConfig) -> Page:
        """Get or create a page, optionally reusing a session."""
        session_id = run_conf.session_id
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        await self._ensure_browser()

        # Build context options
        ctx_kwargs: Dict[str, Any] = {
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
            "ignore_https_errors": self.config.ignore_https_errors,
            "java_script_enabled": self.config.java_script_enabled,
        }

        # User agent: stealth rotation or explicit
        if self.config.stealth_mode and not self.config.user_agent:
            from .stealth import get_random_user_agent
            ctx_kwargs["user_agent"] = get_random_user_agent()
        elif self.config.user_agent:
            ctx_kwargs["user_agent"] = self.config.user_agent

        # Extra HTTP headers
        if self.config.headers:
            ctx_kwargs["extra_http_headers"] = self.config.headers

        context = await self._browser.new_context(**ctx_kwargs)

        # Stealth scripts
        if self.config.stealth_mode:
            from .stealth import apply_stealth
            await apply_stealth(context)

        # Request interception (block images, media, custom patterns)
        if self.config.block_images or self.config.block_media or self.config.blocked_url_patterns:
            await self._setup_route_blocking(context)

        page = await context.new_page()

        # Inject cookies
        if self.config.cookies:
            await context.add_cookies(self.config.cookies)

        # Login flow
        if self.config.login:
            from .login import login_flow, load_cookies, save_cookies
            login_conf = self.config.login
            cookies_loaded = False

            # Try loading saved session cookies first
            if login_conf.cookie_file:
                cookies_loaded = await load_cookies(page, login_conf.cookie_file)

            if not cookies_loaded:
                success = await login_flow(page, login_conf)
                if not success:
                    raise RuntimeError(
                        f"Login failed for {login_conf.login_url} — "
                        f"success_indicator '{login_conf.success_indicator}' not found"
                    )
                # Save cookies for next time
                if login_conf.cookie_file:
                    await save_cookies(page, login_conf.cookie_file)

        # Inject local storage (requires navigating first, done in _fetch_html)
        # Store reference for later use
        page._crawl4ai_local_storage = self.config.local_storage  # type: ignore[attr-defined]

        # Fire on_browser_created hook
        hooks = HookRegistry(run_conf.hooks)
        await hooks.trigger("on_browser_created", page, {"context": context, "config": run_conf})

        if session_id:
            self._sessions[session_id] = page

        return page

    async def _setup_route_blocking(self, context: BrowserContext) -> None:
        """Block requests matching configured patterns."""
        blocked_types = set()
        if self.config.block_images:
            blocked_types.update({"image", "img"})
        if self.config.block_media:
            blocked_types.update({"media", "font", "stylesheet"})

        patterns = self.config.blocked_url_patterns or []

        async def _route_handler(route: Route) -> None:
            req = route.request
            # Block by resource type
            if req.resource_type in blocked_types:
                await route.abort()
                return
            # Block by URL pattern
            for pat in patterns:
                if pat in req.url:
                    await route.abort()
                    return
            await route.continue_()

        await context.route("**/*", _route_handler)

    async def _fetch_html(self, url: str, run_conf: CrawlerRunConfig) -> str:
        """Fetch page HTML, handling raw:// URLs and JS execution."""
        # Support raw HTML input
        if url.startswith("raw://"):
            return url[6:]

        page = await self._get_page(run_conf)
        hooks = HookRegistry(run_conf.hooks)
        hook_ctx: Dict[str, Any] = {"url": url, "config": run_conf}

        try:
            if not run_conf.js_only:
                await page.goto(
                    url,
                    timeout=run_conf.page_timeout,
                    wait_until="domcontentloaded",
                )

            # Inject local storage after first navigation
            local_storage = getattr(page, "_crawl4ai_local_storage", None)
            if local_storage:
                for key, value in local_storage.items():
                    await page.evaluate(
                        f"window.localStorage.setItem({key!r}, {value!r})"
                    )

            # Fire on_page_loaded hook
            await hooks.trigger("on_page_loaded", page, hook_ctx)

            # Simulate human behavior if enabled
            if self.config.simulate_human:
                from .stealth import human_like_delay, random_mouse_movement
                await random_mouse_movement(page, moves=2)
                await human_like_delay(200, 600)

            # Wait for optional CSS selector
            if run_conf.wait_for:
                await page.wait_for_selector(
                    run_conf.wait_for,
                    timeout=run_conf.page_timeout,
                )

            # Execute optional JavaScript snippets
            if run_conf.js_code:
                for js in run_conf.js_code:
                    await page.evaluate(js)

            # Fire after_js_execution hook
            await hooks.trigger("after_js_execution", page, hook_ctx)

            # Small delay for dynamic content to settle
            if run_conf.delay_before_return_html > 0:
                await asyncio.sleep(run_conf.delay_before_return_html)

            # Fire before_return_html hook
            await hooks.trigger("before_return_html", page, hook_ctx)

            # Optionally scope to a CSS selector
            if run_conf.css_selector:
                elements = await page.query_selector_all(run_conf.css_selector)
                parts = []
                for el in elements:
                    parts.append(await el.inner_html())
                html = "\n".join(parts)
            else:
                html = await page.content()

        except Exception as exc:
            await hooks.trigger("on_error", page, {**hook_ctx, "error": str(exc)})
            raise

        finally:
            # Only close page if not part of a session
            if not run_conf.session_id:
                await page.close()

        return html

    async def _run_extraction(
        self, strategy: Any, url: str, html: str
    ) -> str:
        """Run an extraction strategy (sync or async)."""
        if hasattr(strategy, "aextract"):
            return await strategy.aextract(url, html)
        return strategy.extract(url, html)


class AsyncResultStream:
    """Async iterator that yields CrawlResults as they complete."""

    def __init__(
        self,
        crawler: AsyncWebCrawler,
        urls: List[str],
        config: CrawlerRunConfig,
    ) -> None:
        self._crawler = crawler
        self._urls = urls
        self._config = config
        self._queue: asyncio.Queue[Optional[CrawlResult]] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    def __aiter__(self) -> "AsyncResultStream":
        self._task = asyncio.ensure_future(self._produce())
        return self

    async def __anext__(self) -> CrawlResult:
        result = await self._queue.get()
        if result is None:
            raise StopAsyncIteration
        return result

    async def _produce(self) -> None:
        sem = asyncio.Semaphore(10)

        async def _crawl_one(url: str) -> None:
            async with sem:
                res = await self._crawler.arun(url=url, config=self._config)
                await self._queue.put(res)

        tasks = [asyncio.ensure_future(_crawl_one(u)) for u in self._urls]
        await asyncio.gather(*tasks)
        await self._queue.put(None)  # sentinel
