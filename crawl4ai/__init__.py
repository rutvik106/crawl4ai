"""Crawl4AI – An open-source LLM-friendly Web Crawler & Scraper."""

from .async_webcrawler import AsyncWebCrawler
from .browser_config import BrowserConfig
from .cache_mode import CacheMode
from .crawler_run_config import CrawlerRunConfig
from .llm_config import LLMConfig
from .models import CrawlResult, MarkdownResult
from .extraction.css_extraction import JsonCssExtractionStrategy
from .extraction.llm_extraction import LLMExtractionStrategy
from .adaptive_crawler import AdaptiveCrawler
from .markdown_generation_strategy import DefaultMarkdownGenerator
from .hooks import HookRegistry
from .login import LoginConfig, LoginStep
from .output import (
    OutputManager,
    JsonFileOutput,
    CsvFileOutput,
    SQLiteOutput,
    HTMLReportOutput,
    EmailOutput,
    WebhookOutput,
)

__all__ = [
    "AsyncWebCrawler",
    "BrowserConfig",
    "CacheMode",
    "CrawlerRunConfig",
    "LLMConfig",
    "CrawlResult",
    "MarkdownResult",
    "JsonCssExtractionStrategy",
    "LLMExtractionStrategy",
    "AdaptiveCrawler",
    "DefaultMarkdownGenerator",
    "HookRegistry",
    "LoginConfig",
    "LoginStep",
    "OutputManager",
    "JsonFileOutput",
    "CsvFileOutput",
    "SQLiteOutput",
    "HTMLReportOutput",
    "EmailOutput",
    "WebhookOutput",
]

__version__ = "0.1.0"
