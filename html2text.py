"""Minimal local fallback for html2text dependency in test environments."""

from __future__ import annotations

import re
from html import unescape


class HTML2Text:
    """Tiny subset of the html2text.HTML2Text interface used in tests."""

    def __init__(self) -> None:
        self.ignore_links = False
        self.ignore_images = False
        self.ignore_emphasis = False
        self.body_width = 0
        self.skip_internal_links = False
        self.inline_links = True
        self.protect_links = True

    def handle(self, html: str) -> str:
        text = re.sub(r"<\s*br\s*/?>", "\n", html, flags=re.IGNORECASE)
        text = re.sub(r"<\s*/p\s*>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = unescape(text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
