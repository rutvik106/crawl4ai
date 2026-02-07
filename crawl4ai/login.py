"""Login flow helper for automated form-based authentication.

Provides ``LoginConfig`` for declarative login setup and ``login_flow()``
to execute the authentication sequence on a Playwright page.

Usage::

    from crawl4ai import BrowserConfig
    from crawl4ai.login import LoginConfig

    browser_conf = BrowserConfig(
        login=LoginConfig(
            login_url="https://example.com/login",
            credentials={"username": "user@email.com", "password": "secret"},
            steps=[
                LoginStep(selector="#email", value="{username}", action="fill"),
                LoginStep(selector="#password", value="{password}", action="fill"),
                LoginStep(selector="button[type=submit]", action="click"),
            ],
            success_indicator=".dashboard",
        )
    )
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from playwright.async_api import Page


@dataclass
class LoginStep:
    """A single step in a login flow.

    Args:
        selector: CSS selector for the target element.
        action: One of "fill", "click", "check", "select", "wait", "js".
        value: Value to type/select. Use ``{key}`` placeholders to reference
               credentials dict keys, e.g. ``{username}``.
        delay_after: Seconds to wait after this step (default 0.5).
    """
    selector: str = ""
    action: str = "fill"
    value: str = ""
    delay_after: float = 0.5


@dataclass
class LoginConfig:
    """Declarative login configuration.

    Args:
        login_url: URL of the login page.
        credentials: Dict of credential key-value pairs, e.g.
                     ``{"username": "user", "password": "pass"}``.
        steps: Ordered list of ``LoginStep`` actions to perform.
               If empty, falls back to simple mode using
               ``username_selector``, ``password_selector``, ``submit_selector``.
        username_selector: CSS selector for username field (simple mode).
        password_selector: CSS selector for password field (simple mode).
        submit_selector: CSS selector for submit button (simple mode).
        success_indicator: CSS selector that appears after successful login.
        success_timeout: Max ms to wait for success_indicator.
        cookie_file: Optional path to save/load session cookies for persistence.
    """
    login_url: str = ""
    credentials: Dict[str, str] = field(default_factory=dict)
    steps: List[LoginStep] = field(default_factory=list)

    # Simple mode shortcuts
    username_selector: str = ""
    password_selector: str = ""
    submit_selector: str = ""

    success_indicator: str = ""
    success_timeout: int = 10000
    cookie_file: Optional[str] = None


async def login_flow(page: Page, config: LoginConfig) -> bool:
    """Execute a login flow on the given page.

    Returns True if login succeeded (success_indicator found), False otherwise.
    """
    if not config.login_url:
        raise ValueError("login_url is required in LoginConfig")

    # Navigate to login page
    await page.goto(config.login_url, wait_until="domcontentloaded")
    await asyncio.sleep(0.5)

    if config.steps:
        # Step-based login
        for step in config.steps:
            resolved_value = _resolve_value(step.value, config.credentials)
            await _execute_step(page, step, resolved_value)
            if step.delay_after > 0:
                await asyncio.sleep(step.delay_after)
    else:
        # Simple mode: username → password → submit
        creds = config.credentials
        username = creds.get("username", creds.get("email", ""))
        password = creds.get("password", "")

        if config.username_selector and username:
            await page.fill(config.username_selector, username)
            await asyncio.sleep(0.3)

        if config.password_selector and password:
            await page.fill(config.password_selector, password)
            await asyncio.sleep(0.3)

        if config.submit_selector:
            await page.click(config.submit_selector)

    # Wait for success indicator
    if config.success_indicator:
        try:
            await page.wait_for_selector(
                config.success_indicator, timeout=config.success_timeout
            )
            return True
        except Exception:
            return False

    # No indicator — assume success after a brief wait
    await asyncio.sleep(1.0)
    return True


async def save_cookies(page: Page, path: str) -> None:
    """Export browser context cookies to a JSON file."""
    context = page.context
    cookies = await context.cookies()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(cookies, f, indent=2)


async def load_cookies(page: Page, path: str) -> bool:
    """Load cookies from a JSON file into the browser context.

    Returns True if cookies were loaded, False if file doesn't exist.
    """
    if not os.path.exists(path):
        return False
    with open(path, "r") as f:
        cookies = json.load(f)
    await page.context.add_cookies(cookies)
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_value(template: str, credentials: Dict[str, str]) -> str:
    """Replace ``{key}`` placeholders with credential values."""
    result = template
    for key, val in credentials.items():
        result = result.replace(f"{{{key}}}", val)
    return result


async def _execute_step(page: Page, step: LoginStep, value: str) -> None:
    """Execute a single LoginStep action."""
    action = step.action.lower()

    if action == "fill":
        await page.fill(step.selector, value)

    elif action == "click":
        await page.click(step.selector)

    elif action == "check":
        await page.check(step.selector)

    elif action == "select":
        await page.select_option(step.selector, value)

    elif action == "wait":
        timeout = int(float(value) * 1000) if value else 5000
        await page.wait_for_selector(step.selector, timeout=timeout)

    elif action == "js":
        await page.evaluate(value)

    else:
        raise ValueError(f"Unknown login step action: {action!r}")
