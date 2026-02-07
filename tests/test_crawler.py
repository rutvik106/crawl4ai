"""Test AsyncWebCrawler core functionality."""

import json
import pytest
import asyncio

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    JsonCssExtractionStrategy,
)
from tests.conftest import SAMPLE_HTML, SAMPLE_SCHEMA


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
async def test_crawl_raw_html():
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(f"raw://{SAMPLE_HTML}")
        assert result.success is True
        assert "Hello World" in result.markdown.raw_markdown
        assert result.html == SAMPLE_HTML


@pytest.mark.asyncio
async def test_crawl_raw_with_css_extraction():
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url=f"raw://{SAMPLE_HTML}",
            config=CrawlerRunConfig(
                extraction_strategy=JsonCssExtractionStrategy(SAMPLE_SCHEMA),
            ),
        )
        assert result.success is True
        data = json.loads(result.extracted_content)
        assert len(data) == 3
        assert data[0]["title"] == "Item One"


@pytest.mark.asyncio
async def test_crawl_real_url():
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun("https://example.com")
        assert result.success is True
        assert "Example Domain" in result.markdown.raw_markdown
        assert result.html != ""


@pytest.mark.asyncio
async def test_crawl_error_handling():
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun("https://this-domain-does-not-exist-12345.com")
        assert result.success is False
        assert result.error_message is not None


@pytest.mark.asyncio
async def test_crawl_with_browser_config():
    conf = BrowserConfig(headless=True, java_script_enabled=True)
    async with AsyncWebCrawler(config=conf) as crawler:
        result = await crawler.arun("raw://<h1>Test</h1>")
        assert result.success is True
        assert "Test" in str(result.markdown)


@pytest.mark.asyncio
async def test_arun_many_batch():
    urls = [
        "raw://<h1>Page 1</h1>",
        "raw://<h1>Page 2</h1>",
        "raw://<h1>Page 3</h1>",
    ]
    async with AsyncWebCrawler() as crawler:
        results = await crawler.arun_many(urls)
        assert len(results) == 3
        for r in results:
            assert r.success is True


@pytest.mark.asyncio
async def test_arun_many_streaming():
    urls = [
        "raw://<h1>Page A</h1>",
        "raw://<h1>Page B</h1>",
    ]
    conf = CrawlerRunConfig(stream=True)
    async with AsyncWebCrawler() as crawler:
        collected = []
        async for result in await crawler.arun_many(urls, config=conf):
            collected.append(result)
        assert len(collected) == 2
        for r in collected:
            assert r.success is True


@pytest.mark.asyncio
async def test_session_management():
    async with AsyncWebCrawler() as crawler:
        conf = CrawlerRunConfig(session_id="test_session")
        result = await crawler.arun("https://example.com", config=conf)
        assert result.success is True
        assert "test_session" in crawler._sessions
        await crawler.kill_session("test_session")
        assert "test_session" not in crawler._sessions
