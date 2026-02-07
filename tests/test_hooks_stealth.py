"""Test hooks system and stealth utilities."""

import pytest
import asyncio

from crawl4ai.hooks import HookRegistry, HOOK_NAMES
from crawl4ai.stealth import get_random_user_agent
from crawl4ai.login import LoginConfig, LoginStep, _resolve_value


class TestHookRegistry:
    def test_register_valid_hook(self):
        async def my_hook(page, ctx):
            pass
        reg = HookRegistry({"on_page_loaded": my_hook})
        assert "on_page_loaded" in reg._hooks

    def test_register_invalid_hook_raises(self):
        async def my_hook(page, ctx):
            pass
        with pytest.raises(ValueError, match="Unknown hook"):
            HookRegistry({"invalid_hook_name": my_hook})

    def test_all_hook_names_exist(self):
        expected = {
            "on_browser_created",
            "on_page_loaded",
            "after_js_execution",
            "before_return_html",
            "on_error",
        }
        assert HOOK_NAMES == expected

    @pytest.mark.asyncio
    async def test_trigger_fires_hook(self):
        called = []

        async def my_hook(page, ctx):
            called.append(ctx.get("key"))

        reg = HookRegistry({"on_page_loaded": my_hook})
        await reg.trigger("on_page_loaded", None, {"key": "value"})
        assert called == ["value"]

    @pytest.mark.asyncio
    async def test_trigger_skips_unregistered(self):
        reg = HookRegistry()
        # Should not raise
        await reg.trigger("on_page_loaded", None, {})


class TestStealth:
    def test_random_user_agent(self):
        ua = get_random_user_agent()
        assert "Mozilla" in ua
        assert len(ua) > 50

    def test_user_agents_are_varied(self):
        agents = {get_random_user_agent() for _ in range(50)}
        assert len(agents) > 1  # Should get at least 2 different UAs


class TestLoginHelpers:
    def test_resolve_value(self):
        result = _resolve_value("{email}", {"email": "test@example.com"})
        assert result == "test@example.com"

    def test_resolve_value_multiple_placeholders(self):
        result = _resolve_value("{user}:{pass}", {"user": "admin", "pass": "secret"})
        assert result == "admin:secret"

    def test_resolve_value_no_placeholders(self):
        result = _resolve_value("literal_text", {"key": "val"})
        assert result == "literal_text"

    def test_login_config_cookie_file(self):
        lc = LoginConfig(
            login_url="https://example.com",
            cookie_file="/tmp/cookies.json",
        )
        assert lc.cookie_file == "/tmp/cookies.json"

    def test_login_step_actions(self):
        actions = ["fill", "click", "check", "select", "wait", "js"]
        for action in actions:
            step = LoginStep(selector="#el", action=action, value="val")
            assert step.action == action
