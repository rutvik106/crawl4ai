from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional, List, Any, TYPE_CHECKING

from .cache_mode import CacheMode

if TYPE_CHECKING:
    from .markdown_generation_strategy import DefaultMarkdownGenerator


@dataclass
class CrawlerRunConfig:
    """Configuration for a single crawl run."""
    cache_mode: CacheMode = CacheMode.BYPASS
    markdown_generator: Optional[Any] = None
    extraction_strategy: Optional[Any] = None
    word_count_threshold: int = 200
    css_selector: Optional[str] = None
    excluded_tags: List[str] = field(default_factory=lambda: ["script", "style", "nav", "footer"])
    js_code: Optional[List[str]] = None
    wait_for: Optional[str] = None
    js_only: bool = False
    session_id: Optional[str] = None
    page_timeout: int = 60000
    delay_before_return_html: float = 0.1
    mean_delay: float = 0.0
    max_range: float = 0.0
    stream: bool = False
    verbose: bool = False
    hooks: Optional[dict] = None
    output: Optional[List[Any]] = None

    # Fields that should be shared (not deep-copied) across clones
    _SHALLOW_FIELDS = {"output", "extraction_strategy", "markdown_generator", "hooks"}

    def clone(self, **overrides) -> "CrawlerRunConfig":
        """Create a copy of this config with optional overrides."""
        # Temporarily remove non-copyable fields
        saved = {}
        for fname in self._SHALLOW_FIELDS:
            saved[fname] = getattr(self, fname)
            setattr(self, fname, None)

        new = copy.deepcopy(self)

        # Restore originals on both self and clone
        for fname, val in saved.items():
            setattr(self, fname, val)
            setattr(new, fname, val)

        for k, v in overrides.items():
            if hasattr(new, k):
                setattr(new, k, v)
            else:
                raise AttributeError(f"CrawlerRunConfig has no attribute '{k}'")
        return new
