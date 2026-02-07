"""Markdown generation strategies for converting HTML to Markdown."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

import html2text

if TYPE_CHECKING:
    from .content_filter_strategy import ContentFilterStrategy

from .models import MarkdownResult


@dataclass
class DefaultMarkdownGenerator:
    """Converts HTML to Markdown, optionally applying a content filter.

    Args:
        content_filter: An optional ContentFilterStrategy to produce fit_markdown.
        options: Extra options forwarded to html2text.
    """
    content_filter: Optional["ContentFilterStrategy"] = None
    options: dict = field(default_factory=dict)

    def convert(self, html: str) -> MarkdownResult:
        """Convert HTML string to a MarkdownResult."""
        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = False
        converter.ignore_emphasis = False
        converter.body_width = 0  # no wrapping
        converter.skip_internal_links = False
        converter.inline_links = True
        converter.protect_links = True

        # Apply any user-supplied options
        for key, value in self.options.items():
            setattr(converter, key, value)

        raw_md = converter.handle(html).strip()

        fit_md = ""
        if self.content_filter:
            fit_md = self.content_filter.filter(raw_md)

        return MarkdownResult(raw_markdown=raw_md, fit_markdown=fit_md)
