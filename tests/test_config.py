"""Test configuration classes."""

from crawl4ai import (
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    LoginConfig,
    LoginStep,
    LLMConfig,
    JsonFileOutput,
    SQLiteOutput,
)


def test_browser_config_defaults():
    conf = BrowserConfig()
    assert conf.headless is True
    assert conf.browser_type == "chromium"
    assert conf.stealth_mode is False
    assert conf.cookies is None
    assert conf.block_images is False


def test_browser_config_with_stealth():
    conf = BrowserConfig(stealth_mode=True, simulate_human=True, block_images=True)
    assert conf.stealth_mode is True
    assert conf.simulate_human is True
    assert conf.block_images is True


def test_browser_config_with_login():
    login = LoginConfig(
        login_url="https://example.com/login",
        credentials={"user": "test", "pass": "secret"},
        username_selector="#user",
        password_selector="#pass",
        submit_selector="button",
    )
    conf = BrowserConfig(login=login)
    assert conf.login.login_url == "https://example.com/login"
    assert conf.login.credentials["user"] == "test"


def test_crawler_run_config_defaults():
    conf = CrawlerRunConfig()
    assert conf.cache_mode == CacheMode.BYPASS
    assert conf.page_timeout == 60000
    assert conf.stream is False
    assert conf.hooks is None
    assert conf.output is None


def test_crawler_run_config_clone_basic():
    conf = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
    clone = conf.clone(stream=True)
    assert clone.stream is True
    assert conf.stream is False  # Original unchanged
    assert clone.cache_mode == CacheMode.BYPASS


def test_crawler_run_config_clone_with_output():
    """Ensure clone works with non-deepcopyable output backends."""
    outputs = [JsonFileOutput(path="/tmp/test_clone.json")]
    conf = CrawlerRunConfig(output=outputs, stream=False)
    clone = conf.clone(stream=True)
    assert clone.stream is True
    assert clone.output is outputs  # Shared reference, not deep copy


def test_crawler_run_config_clone_with_sqlite():
    """SQLite connections can't be deepcopied — clone should handle this."""
    import os
    db_path = "/tmp/test_clone_sqlite.db"
    outputs = [SQLiteOutput(db_path=db_path)]
    conf = CrawlerRunConfig(output=outputs)
    clone = conf.clone(stream=True)
    assert clone.stream is True
    assert clone.output is outputs
    outputs[0].finalize()
    if os.path.exists(db_path):
        os.remove(db_path)


def test_crawler_run_config_clone_invalid_attr():
    conf = CrawlerRunConfig()
    try:
        conf.clone(nonexistent_field=True)
        assert False, "Should have raised AttributeError"
    except AttributeError:
        pass


def test_cache_mode_values():
    assert CacheMode.ENABLED.value == "enabled"
    assert CacheMode.BYPASS.value == "bypass"
    assert CacheMode.READ_ONLY.value == "read_only"
    assert CacheMode.WRITE_ONLY.value == "write_only"


def test_llm_config():
    conf = LLMConfig(provider="groq/llama-3.1-8b-instant", api_token="test_key")
    assert conf.provider == "groq/llama-3.1-8b-instant"
    assert conf.api_token == "test_key"


def test_login_step_defaults():
    step = LoginStep(selector="#email", action="fill", value="{email}")
    assert step.action == "fill"
    assert step.delay_after == 0.5


def test_login_config_simple_mode():
    lc = LoginConfig(
        login_url="https://example.com/login",
        credentials={"username": "u", "password": "p"},
        username_selector="#user",
        password_selector="#pass",
        submit_selector="button",
        success_indicator=".dashboard",
    )
    assert lc.steps == []
    assert lc.success_indicator == ".dashboard"


def test_login_config_step_mode():
    lc = LoginConfig(
        login_url="https://example.com/login",
        credentials={"email": "u@test.com", "pass": "secret"},
        steps=[
            LoginStep(selector="#email", action="fill", value="{email}"),
            LoginStep(selector="button.next", action="click"),
            LoginStep(selector="#pass", action="fill", value="{pass}"),
            LoginStep(selector="button[type=submit]", action="click"),
        ],
    )
    assert len(lc.steps) == 4
