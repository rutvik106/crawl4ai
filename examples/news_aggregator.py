#!/usr/bin/env python3
"""
News Aggregator Demo
====================
Crawls multiple news sites concurrently using Crawl4AI's arun_many(),
extracts headlines with Groq LLM, and outputs a unified JSON feed.

Usage:
    export GROQ_API_KEY="your-key"
    python examples/news_aggregator.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    LLMConfig,
    LLMExtractionStrategy,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "groq/llama-3.1-8b-instant"

NEWS_SOURCES: List[Dict[str, str]] = [
    {
        "name": "Hacker News",
        "url": "https://news.ycombinator.com",
        "focus": "tech and startup news",
    },
    {
        "name": "BBC News",
        "url": "https://www.bbc.com/news",
        "focus": "world news headlines",
    },
    {
        "name": "Reuters",
        "url": "https://www.reuters.com",
        "focus": "world and business news",
    },
    {
        "name": "TechCrunch",
        "url": "https://techcrunch.com",
        "focus": "technology and startup news",
    },
]

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class NewsArticle(BaseModel):
    title: str = Field(..., description="The headline / title of the article")
    source: str = Field(..., description="Publisher or website name")
    category: str = Field("general", description="Category: tech, world, business, science, etc.")
    summary: str = Field("", description="One-sentence summary if available")


class NewsFeed(BaseModel):
    articles: List[NewsArticle]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def build_extraction_strategy() -> LLMExtractionStrategy:
    return LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider=GROQ_MODEL,
            api_token=GROQ_API_KEY,
        ),
        schema=NewsArticle.model_json_schema(),
        extraction_type="schema",
        instruction=(
            "Extract the top news headlines from this page. "
            "For each article, extract the title, source/publisher name, "
            "a category (tech, world, business, science, sports, entertainment, or general), "
            "and a brief one-sentence summary if possible. "
            "Return a JSON array of objects. Include up to 10 headlines."
        ),
        extra_args={"temperature": 0, "max_tokens": 4000},
        content_length_limit=12000,
    )


async def crawl_and_extract() -> List[Dict]:
    """Crawl all news sources concurrently and extract headlines."""

    browser_conf = BrowserConfig(headless=True, java_script_enabled=True)

    # We create per-URL configs since each needs its own LLM strategy instance
    urls = [src["url"] for src in NEWS_SOURCES]

    run_conf = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        delay_before_return_html=3.0,
        extraction_strategy=build_extraction_strategy(),
    )

    all_articles: List[Dict] = []

    print(f"\n{'='*60}")
    print(f"  📰  Crawl4AI News Aggregator")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    print(f"Crawling {len(urls)} sources concurrently...\n")

    async with AsyncWebCrawler(config=browser_conf) as crawler:
        # Stream results as they complete
        stream_conf = run_conf.clone(stream=True)
        async for result in await crawler.arun_many(urls, config=stream_conf):
            # Find source name
            source_info = next(
                (s for s in NEWS_SOURCES if s["url"] == result.url), None
            )
            source_name = source_info["name"] if source_info else result.url

            if not result.success:
                print(f"  [FAIL] {source_name}: {result.error_message}\n")
                continue

            if not result.extracted_content:
                print(f"  [WARN] {source_name}: No extracted content\n")
                continue

            try:
                articles = json.loads(result.extracted_content)
                if isinstance(articles, dict):
                    articles = articles.get("articles", [articles])
            except json.JSONDecodeError as e:
                print(f"  [WARN] {source_name}: JSON parse error: {e}\n")
                continue

            print(f"  [OK] {source_name}: {len(articles)} headlines extracted")

            for article in articles:
                article["_source_url"] = result.url
                if not article.get("source"):
                    article["source"] = source_name
                all_articles.append(article)

    return all_articles


def display_feed(articles: List[Dict]) -> None:
    """Pretty-print the aggregated news feed."""
    print(f"\n{'='*60}")
    print(f"  AGGREGATED FEED: {len(articles)} articles")
    print(f"{'='*60}\n")

    # Group by category
    by_category: Dict[str, List[Dict]] = {}
    for a in articles:
        cat = a.get("category", "general").lower()
        by_category.setdefault(cat, []).append(a)

    for category, items in sorted(by_category.items()):
        print(f"  [{category.upper()}]")
        for i, item in enumerate(items, 1):
            title = item.get("title", "N/A")
            source = item.get("source", "")
            summary = item.get("summary", "")
            print(f"    {i}. {title}")
            print(f"       — {source}")
            if summary:
                print(f"       {summary}")
            print()
        print()


def save_feed(articles: List[Dict], path: str) -> None:
    """Save the feed as a JSON file."""
    feed = {
        "generated_at": datetime.now().isoformat(),
        "total_articles": len(articles),
        "articles": articles,
    }
    with open(path, "w") as f:
        json.dump(feed, f, indent=2, ensure_ascii=False)
    print(f"Feed saved to {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    articles = await crawl_and_extract()

    if not articles:
        print("\nNo articles extracted. Check your network or API key.")
        return

    display_feed(articles)

    # Save JSON feed
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "news_feed.json",
    )
    save_feed(articles, output_path)


if __name__ == "__main__":
    asyncio.run(main())
