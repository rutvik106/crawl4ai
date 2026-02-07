"""Base class for extraction strategies."""

from __future__ import annotations

from typing import Any, Optional


class ExtractionStrategy:
    """Abstract base for all extraction strategies."""

    def extract(self, url: str, html: str, *args: Any, **kwargs: Any) -> str:
        """Extract data from HTML and return a JSON string."""
        raise NotImplementedError

    async def aextract(self, url: str, html: str, *args: Any, **kwargs: Any) -> str:
        """Async variant – defaults to calling sync extract."""
        return self.extract(url, html, *args, **kwargs)
