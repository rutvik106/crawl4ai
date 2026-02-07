"""Test that all public exports import correctly."""


def test_core_imports():
    from crawl4ai import (
        AsyncWebCrawler,
        BrowserConfig,
        CacheMode,
        CrawlerRunConfig,
        LLMConfig,
        CrawlResult,
        MarkdownResult,
    )
    assert AsyncWebCrawler is not None
    assert CacheMode.BYPASS.value == "bypass"


def test_extraction_imports():
    from crawl4ai import JsonCssExtractionStrategy, LLMExtractionStrategy
    assert JsonCssExtractionStrategy is not None
    assert LLMExtractionStrategy is not None


def test_feature_imports():
    from crawl4ai import (
        AdaptiveCrawler,
        DefaultMarkdownGenerator,
        HookRegistry,
        LoginConfig,
        LoginStep,
    )
    assert AdaptiveCrawler is not None
    assert LoginConfig is not None


def test_output_imports():
    from crawl4ai import (
        OutputManager,
        JsonFileOutput,
        CsvFileOutput,
        SQLiteOutput,
        HTMLReportOutput,
        EmailOutput,
        WebhookOutput,
    )
    assert OutputManager is not None
    assert SQLiteOutput is not None


def test_content_filter_imports():
    from crawl4ai.content_filter_strategy import PruningContentFilter, BM25ContentFilter
    assert PruningContentFilter is not None
    assert BM25ContentFilter is not None


def test_stealth_imports():
    from crawl4ai.stealth import (
        get_random_user_agent,
        apply_stealth,
        human_like_delay,
        human_like_scroll,
        random_mouse_movement,
    )
    assert callable(get_random_user_agent)
