"""Adaptive crawler that intelligently determines when sufficient information has been gathered."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from .async_webcrawler import AsyncWebCrawler

from .crawler_run_config import CrawlerRunConfig
from .cache_mode import CacheMode
from .models import CrawlResult


@dataclass
class AdaptiveResult:
    """Result of an adaptive crawl session."""
    crawled_urls: List[str] = field(default_factory=list)
    results: List[CrawlResult] = field(default_factory=list)
    combined_markdown: str = ""


class AdaptiveCrawler:
    """Intelligent adaptive crawler that automatically stops when sufficient info is gathered.

    Usage::

        async with AsyncWebCrawler() as crawler:
            adaptive = AdaptiveCrawler(crawler)
            result = await adaptive.digest(
                start_url="https://docs.python.org/3/",
                query="async context managers"
            )
            adaptive.print_stats()
    """

    def __init__(
        self,
        crawler: "AsyncWebCrawler",
        max_pages: int = 20,
        target_confidence: float = 0.85,
        relevance_threshold: float = 0.3,
    ) -> None:
        self.crawler = crawler
        self.max_pages = max_pages
        self.target_confidence = target_confidence
        self.relevance_threshold = relevance_threshold

        # State
        self.confidence: float = 0.0
        self._crawled_urls: List[str] = []
        self._visited: Set[str] = set()
        self._relevant_content: List[str] = []
        self._stats: Dict[str, Any] = {}

    async def digest(
        self,
        start_url: str,
        query: str,
        config: Optional[CrawlerRunConfig] = None,
    ) -> AdaptiveResult:
        """Start an adaptive crawl from *start_url* guided by *query*.

        The crawler follows relevant links and stops when confidence
        reaches the target or the page limit is hit.
        """
        run_conf = config or CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
        result = AdaptiveResult()

        frontier: List[str] = [start_url]
        query_terms = set(query.lower().split())

        while frontier and len(self._crawled_urls) < self.max_pages:
            url = frontier.pop(0)
            if url in self._visited:
                continue
            self._visited.add(url)

            crawl_result = await self.crawler.arun(url=url, config=run_conf)
            if not crawl_result.success:
                continue

            self._crawled_urls.append(url)
            result.results.append(crawl_result)
            result.crawled_urls.append(url)

            # Score relevance
            md_text = str(crawl_result.markdown).lower()
            relevance = self._compute_relevance(md_text, query_terms)

            if relevance >= self.relevance_threshold:
                self._relevant_content.append(str(crawl_result.markdown))

            # Update confidence
            self.confidence = self._compute_confidence(query_terms)
            if self.confidence >= self.target_confidence:
                break

            # Extract and score links
            new_links = self._extract_links(crawl_result.html, url)
            scored = [(l, self._score_link(l, query_terms)) for l in new_links]
            scored.sort(key=lambda x: x[1], reverse=True)
            for link, score in scored:
                if link not in self._visited and score > 0:
                    frontier.append(link)

        result.combined_markdown = "\n\n---\n\n".join(self._relevant_content)

        self._stats = {
            "pages_crawled": len(self._crawled_urls),
            "relevant_pages": len(self._relevant_content),
            "confidence": self.confidence,
            "urls_visited": list(self._crawled_urls),
        }

        return result

    def print_stats(self) -> None:
        """Print crawl statistics."""
        print(f"Pages crawled: {self._stats.get('pages_crawled', 0)}")
        print(f"Relevant pages: {self._stats.get('relevant_pages', 0)}")
        print(f"Confidence: {self.confidence:.0%}")

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compute_relevance(text: str, query_terms: Set[str]) -> float:
        if not query_terms or not text:
            return 0.0
        text_words = set(text.split())
        overlap = len(query_terms & text_words)
        return overlap / len(query_terms)

    def _compute_confidence(self, query_terms: Set[str]) -> float:
        if not self._relevant_content:
            return 0.0

        combined = " ".join(self._relevant_content).lower()
        combined_words = set(combined.split())
        term_coverage = len(query_terms & combined_words) / max(len(query_terms), 1)

        volume_factor = min(len(self._relevant_content) / 5.0, 1.0)

        return min(term_coverage * 0.7 + volume_factor * 0.3, 1.0)

    @staticmethod
    def _extract_links(html: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html, "lxml")
        links: List[str] = []
        base_domain = urlparse(base_url).netloc

        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(base_url, href)
            parsed = urlparse(full)
            if parsed.netloc == base_domain and parsed.scheme in ("http", "https"):
                clean = parsed._replace(fragment="").geturl()
                if clean not in links:
                    links.append(clean)
        return links

    @staticmethod
    def _score_link(url: str, query_terms: Set[str]) -> float:
        url_lower = url.lower()
        score = 0.0
        for term in query_terms:
            if term in url_lower:
                score += 1.0
        return score / max(len(query_terms), 1)
