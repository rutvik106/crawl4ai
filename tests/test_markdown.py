"""Test markdown generation and content filtering."""

from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter, BM25ContentFilter
from tests.conftest import SAMPLE_HTML


def test_default_markdown_generator():
    gen = DefaultMarkdownGenerator()
    result = gen.convert(SAMPLE_HTML)
    assert len(result.raw_markdown) > 0
    assert "Hello World" in result.raw_markdown
    assert result.fit_markdown == ""  # No filter configured


def test_markdown_with_pruning_filter():
    gen = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.3, threshold_type="fixed")
    )
    result = gen.convert(SAMPLE_HTML)
    assert len(result.raw_markdown) > 0
    assert len(result.fit_markdown) > 0
    assert len(result.fit_markdown) <= len(result.raw_markdown)


def test_markdown_result_string_behavior():
    gen = DefaultMarkdownGenerator()
    result = gen.convert("<h1>Title</h1><p>Body text</p>")
    assert "Title" in str(result)
    assert len(result) > 0
    assert "Title" in result[:50]


def test_pruning_filter_removes_boilerplate():
    filt = PruningContentFilter(threshold=0.3)
    text = "copyright 2026 all rights reserved\n\nThis is a substantial paragraph with enough words to be considered meaningful content by the scoring algorithm."
    result = filt.filter(text)
    assert "copyright" not in result.lower()


def test_pruning_filter_dynamic_threshold():
    filt = PruningContentFilter(threshold=0.2, threshold_type="dynamic")
    text = "Short block\n\nThis is a much longer block with plenty of natural language text that should score well in the content quality heuristic."
    result = filt.filter(text)
    assert len(result) > 0


def test_bm25_filter_with_query():
    filt = BM25ContentFilter(user_query="python async", bm25_threshold=0.5)
    text = "Some unrelated content about cooking.\n\nPython async programming is powerful for web crawling."
    result = filt.filter(text)
    assert "python" in result.lower() or "async" in result.lower()


def test_bm25_filter_no_query_returns_original():
    filt = BM25ContentFilter(user_query=None)
    text = "Some content here."
    assert filt.filter(text) == text


def test_empty_html():
    gen = DefaultMarkdownGenerator()
    result = gen.convert("")
    assert result.raw_markdown == ""
