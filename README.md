# Crawl4AI

An open-source LLM-friendly Web Crawler & Scraper.

## Features

- **Async crawling** with headless Chromium via Playwright
- **Automatic HTML-to-Markdown** conversion with configurable content filters
- **CSS/XPath extraction** for structured JSON output
- **LLM-based extraction** supporting OpenAI, Ollama, and other providers
- **Adaptive crawling** with automatic stopping and confidence scoring
- **Multi-URL concurrency** with memory-adaptive dispatching
- **Dynamic page support** with JavaScript execution and session management

## Installation

```bash
pip install -e .
playwright install chromium
```

## Quick Start

```python
import asyncio
from crawl4ai import AsyncWebCrawler

async def main():
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun("https://example.com")
        print(result.markdown[:300])

if __name__ == "__main__":
    asyncio.run(main())
```

## Documentation

See the [Getting Started tutorial](docs/tutorials/getting-started.md) for a full walkthrough.
