"""Tests for job engine fixes — async extraction, timeout, concurrency."""

import asyncio
import json
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from crawl4ai.extraction.llm_extraction import LLMExtractionStrategy
from crawl4ai.llm_config import LLMConfig
from crawl4ai.deep_crawler import smart_extract, _heuristic_filter
from dashboard.engine import _attach_article_urls


# ── Fix 1: smart_extract uses async aextract, not sync extract ──


@pytest.mark.asyncio
async def test_smart_extract_calls_aextract_not_extract():
    """smart_extract must await strategy.aextract(), never call strategy.extract().
    
    Calling the sync extract() from an async context blocks the event loop,
    preventing asyncio.wait_for timeouts from firing and causing jobs to hang.
    """
    mock_strategy = MagicMock(spec=LLMExtractionStrategy)
    mock_strategy.content_length_limit = 50000
    mock_strategy.instruction = "test"
    mock_strategy.schema = None

    # aextract is the async method that should be called
    mock_strategy.aextract = AsyncMock(return_value='[{"title": "Test Article", "summary": "A test"}]')

    from crawl4ai.crawler_run_config import CrawlerRunConfig
    run_conf = CrawlerRunConfig(extraction_strategy=mock_strategy)

    result = await smart_extract("Some test content about news articles", run_conf)

    # Verify aextract was called (async path)
    assert mock_strategy.aextract.called, "smart_extract should call aextract (async), not extract (sync)"
    # Verify extract was NOT called (sync path that blocks event loop)
    assert not mock_strategy.extract.called, "smart_extract must NOT call sync extract()"


@pytest.mark.asyncio
async def test_smart_extract_empty_content():
    """smart_extract should return '[]' for empty content without calling LLM."""
    mock_strategy = MagicMock(spec=LLMExtractionStrategy)
    mock_strategy.aextract = AsyncMock()
    
    from crawl4ai.crawler_run_config import CrawlerRunConfig
    run_conf = CrawlerRunConfig(extraction_strategy=mock_strategy)
    
    result = await smart_extract("", run_conf)
    assert result == "[]"
    assert not mock_strategy.aextract.called


@pytest.mark.asyncio
async def test_smart_extract_chunked_content_uses_aextract():
    """When content is too large, chunked extraction must also use aextract."""
    mock_strategy = MagicMock(spec=LLMExtractionStrategy)
    mock_strategy.content_length_limit = 100  # Force chunking
    mock_strategy.instruction = "test"
    mock_strategy.schema = None
    mock_strategy.aextract = AsyncMock(return_value='[{"title": "Chunk Article"}]')

    from crawl4ai.crawler_run_config import CrawlerRunConfig
    run_conf = CrawlerRunConfig(extraction_strategy=mock_strategy)

    long_content = "A" * 500  # Exceeds content_length_limit of 100
    result = await smart_extract(long_content, run_conf)

    assert mock_strategy.aextract.called
    assert not mock_strategy.extract.called


# ── Fix 2: LLM timeout ──


def test_llm_extraction_sets_default_timeout():
    """LLMExtractionStrategy.aextract must set a timeout on litellm calls."""
    strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(provider="groq/test-model", api_token="fake"),
        extra_args={"temperature": 0},
    )

    # Capture the kwargs passed to litellm.acompletion
    captured_kwargs = {}

    async def mock_acompletion(**kwargs):
        captured_kwargs.update(kwargs)
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = '[]'
        return mock_resp

    with patch("litellm.acompletion", side_effect=mock_acompletion):
        asyncio.run(strategy.aextract("test", "test content"))

    assert "timeout" in captured_kwargs, "litellm.acompletion must be called with a timeout"
    assert captured_kwargs["timeout"] == 120


# ── Fix 3: extra_args mutation ──


def test_extra_args_not_mutated():
    """extra_args dict must not be mutated by extract calls."""
    original_extra = {"temperature": 0, "max_tokens": 4000, "extra_headers": {"X-Test": "1"}}
    strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(provider="groq/test-model", api_token="fake"),
        extra_args=original_extra.copy(),
    )

    async def mock_acompletion(**kwargs):
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = '[]'
        return mock_resp

    with patch("litellm.acompletion", side_effect=mock_acompletion):
        asyncio.run(strategy.aextract("test", "content"))
        # Call again to ensure no state corruption
        asyncio.run(strategy.aextract("test", "content"))

    assert "extra_headers" in strategy.extra_args, "extra_args should not lose extra_headers after extraction"
    assert strategy.extra_args["extra_headers"] == {"X-Test": "1"}


# ── Fix 4: heuristic filter ──


def test_heuristic_filter_removes_noise():
    """Heuristic filter should remove obvious noise items."""
    articles = [
        {"title": "Real News Article About Pharma Company Earnings", "summary": "A real article"},
        {"title": "Subscribe", "summary": ""},
        {"title": "Follow Us", "summary": ""},
        {"title": "AB", "summary": "too short"},  # < 8 chars
        {"title": "SingleWord", "summary": ""},  # no spaces
    ]
    filtered = _heuristic_filter(articles)
    assert len(filtered) == 1
    assert filtered[0]["title"] == "Real News Article About Pharma Company Earnings"


def test_attach_article_urls_matches_exact_headline():
    articles = [{"title": "Company Announces Positive Phase 3 Results"}]
    links = [{
        "text": "Company Announces Positive Phase 3 Results",
        "url": "https://example.com/news/phase-3-results",
    }]

    attached = _attach_article_urls(articles, links)

    assert attached == 1
    assert articles[0]["url"] == "https://example.com/news/phase-3-results"


def test_attach_article_urls_matches_minor_headline_variation():
    articles = [{"title": "Lilly reports positive topline results for retatrutide trials"}]
    links = [{
        "text": "Lilly reports positive topline results from retatrutide Phase 3 trials",
        "url": "https://example.com/news/retatrutide",
    }]

    attached = _attach_article_urls(articles, links)

    assert attached == 1
    assert articles[0]["url"] == "https://example.com/news/retatrutide"


def test_attach_article_urls_preserves_existing_source_alias():
    articles = [{
        "title": "Existing Article",
        "article_url": "https://publisher.example/original",
    }]

    attached = _attach_article_urls(articles, [])

    assert attached == 0
    assert articles[0]["url"] == "https://publisher.example/original"


# ── Fix 5: a broken LLM must not masquerade as "no news today" ──
#
# Regression guard for the outage where litellm/pydantic became incompatible and
# every completion() raised. smart_extract swallowed the errors, returned zero
# articles, and the job was recorded as "completed" — indistinguishable from a
# quiet news day, so three days of empty briefs went unnoticed.


def _mock_strategy(limit=50000, side_effect=None, return_value=None):
    strategy = MagicMock(spec=LLMExtractionStrategy)
    strategy.content_length_limit = limit
    strategy.instruction = "test"
    strategy.schema = None
    strategy.aextract = AsyncMock(side_effect=side_effect, return_value=return_value)
    return strategy


def _run_conf(strategy):
    from crawl4ai.crawler_run_config import CrawlerRunConfig
    return CrawlerRunConfig(extraction_strategy=strategy)


@pytest.mark.asyncio
async def test_smart_extract_reports_llm_failures_in_stats():
    """Every LLM call failing must be visible in stats, not silently swallowed."""
    boom = RuntimeError(
        "litellm.APIConnectionError: `Message` is not fully defined; you should "
        "define `ChatCompletionReasoningSummaryTextBlock`"
    )
    strategy = _mock_strategy(side_effect=boom)
    stats = {}

    result = await smart_extract("Plenty of real news content here", _run_conf(strategy), stats=stats)

    assert json.loads(result) == []
    assert stats["llm_calls"] == 1
    assert stats["llm_errors"] == 1
    assert "Message` is not fully defined" in stats["llm_last_error"]


@pytest.mark.asyncio
async def test_smart_extract_reports_llm_failures_across_all_chunks():
    """Chunked extraction must count a failure for each failed chunk."""
    # _chunk_content splits on blank lines, so the content needs real paragraphs.
    content = "\n\n".join(["A" * 80] * 5)
    strategy = _mock_strategy(limit=100, side_effect=RuntimeError("api exploded"))
    stats = {}

    await smart_extract(content, _run_conf(strategy), stats=stats)

    assert stats["llm_calls"] == 5
    assert stats["llm_errors"] == stats["llm_calls"]
    assert stats["llm_last_error"] == "api exploded"


@pytest.mark.asyncio
async def test_smart_extract_records_zero_errors_on_a_quiet_news_day():
    """A working LLM that legitimately finds nothing must NOT look like a failure."""
    strategy = _mock_strategy(return_value="[]")
    stats = {}

    await smart_extract("Some content with no fresh news", _run_conf(strategy), stats=stats)

    assert stats["llm_calls"] == 1
    assert stats["llm_errors"] == 0
    assert "llm_last_error" not in stats


@pytest.mark.asyncio
async def test_smart_extract_partial_chunk_failure_keeps_articles():
    """One bad chunk must not discard the articles recovered from healthy chunks."""
    content = "\n\n".join(["A" * 80] * 3)
    strategy = _mock_strategy(
        limit=100,
        side_effect=[
            RuntimeError("chunk 1 died"),
            '[{"title": "A Real Recovered Headline"}]',
            '[{"title": "Another Genuine Headline Here"}]',
        ],
    )
    stats = {}

    result = await smart_extract(content, _run_conf(strategy), stats=stats)

    assert stats["llm_errors"] < stats["llm_calls"]
    assert any(a["title"] == "A Real Recovered Headline" for a in json.loads(result))
