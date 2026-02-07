"""Shared fixtures for crawl4ai tests."""

import pytest


SAMPLE_HTML = """
<html>
<head><title>Test Page</title></head>
<body>
    <h1>Hello World</h1>
    <p>This is a test page with enough words to pass thresholds for content filtering and quality scoring in the pruning filter.</p>
    <div class="item">
        <h2>Item One</h2>
        <a href="https://example.com/1">Link 1</a>
        <p>Description of item one with some meaningful content here.</p>
    </div>
    <div class="item">
        <h2>Item Two</h2>
        <a href="https://example.com/2">Link 2</a>
        <p>Description of item two with some meaningful content here.</p>
    </div>
    <div class="item">
        <h2>Item Three</h2>
        <a href="https://example.com/3">Link 3</a>
        <p>Description of item three with some meaningful content here.</p>
    </div>
    <nav>Skip to content | Home | About</nav>
    <footer>Copyright 2026 Test Corp</footer>
</body>
</html>
"""

SAMPLE_SCHEMA = {
    "name": "Test Items",
    "baseSelector": "div.item",
    "fields": [
        {"name": "title", "selector": "h2", "type": "text"},
        {"name": "link", "selector": "a", "type": "attribute", "attribute": "href"},
        {"name": "description", "selector": "p", "type": "text"},
    ],
}
