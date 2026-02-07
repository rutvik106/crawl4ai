"""Test CSS extraction strategy."""

import json

from crawl4ai import JsonCssExtractionStrategy
from tests.conftest import SAMPLE_HTML, SAMPLE_SCHEMA


def test_css_extraction_basic():
    strategy = JsonCssExtractionStrategy(SAMPLE_SCHEMA)
    result = strategy.extract("https://example.com", SAMPLE_HTML)
    data = json.loads(result)
    assert len(data) == 3
    assert data[0]["title"] == "Item One"
    assert data[1]["title"] == "Item Two"
    assert data[2]["title"] == "Item Three"


def test_css_extraction_attributes():
    strategy = JsonCssExtractionStrategy(SAMPLE_SCHEMA)
    result = strategy.extract("", SAMPLE_HTML)
    data = json.loads(result)
    assert data[0]["link"] == "https://example.com/1"
    assert data[1]["link"] == "https://example.com/2"


def test_css_extraction_descriptions():
    strategy = JsonCssExtractionStrategy(SAMPLE_SCHEMA)
    result = strategy.extract("", SAMPLE_HTML)
    data = json.loads(result)
    assert "item one" in data[0]["description"].lower()


def test_css_extraction_no_match():
    schema = {
        "name": "Empty",
        "baseSelector": "div.nonexistent",
        "fields": [{"name": "text", "selector": "p", "type": "text"}],
    }
    strategy = JsonCssExtractionStrategy(schema)
    result = strategy.extract("", SAMPLE_HTML)
    data = json.loads(result)
    assert data == []


def test_css_extraction_html_type():
    schema = {
        "name": "HTML Items",
        "baseSelector": "div.item",
        "fields": [{"name": "inner", "selector": "h2", "type": "html"}],
    }
    strategy = JsonCssExtractionStrategy(schema)
    result = strategy.extract("", SAMPLE_HTML)
    data = json.loads(result)
    assert "<h2>" in data[0]["inner"]


def test_css_extraction_missing_field():
    schema = {
        "name": "Missing",
        "baseSelector": "div.item",
        "fields": [{"name": "img", "selector": "img", "type": "attribute", "attribute": "src"}],
    }
    strategy = JsonCssExtractionStrategy(schema)
    result = strategy.extract("", SAMPLE_HTML)
    data = json.loads(result)
    assert data[0]["img"] is None
