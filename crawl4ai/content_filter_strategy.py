"""Content filter strategies for post-processing markdown output."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


class ContentFilterStrategy:
    """Base class for content filters."""

    def filter(self, text: str) -> str:
        raise NotImplementedError


@dataclass
class PruningContentFilter(ContentFilterStrategy):
    """Prunes low-quality or boilerplate content from markdown.

    Uses a scoring heuristic based on text density, link density,
    and structural signals to keep only high-quality content blocks.

    Args:
        threshold: Minimum quality score for a block to be kept.
        threshold_type: "fixed" uses the threshold as-is;
                        "dynamic" adapts based on overall page quality.
        min_word_threshold: Minimum words in a block to consider it.
    """
    threshold: float = 0.48
    threshold_type: str = "fixed"
    min_word_threshold: int = 0

    def filter(self, text: str) -> str:
        if not text:
            return ""

        blocks = self._split_blocks(text)
        scored = [(b, self._score_block(b)) for b in blocks]

        effective_threshold = self.threshold
        if self.threshold_type == "dynamic" and scored:
            avg_score = sum(s for _, s in scored) / len(scored)
            effective_threshold = max(self.threshold, avg_score * 0.6)

        kept: List[str] = []
        for block, score in scored:
            word_count = len(block.split())
            if word_count < self.min_word_threshold:
                continue
            if score >= effective_threshold:
                kept.append(block)

        return "\n\n".join(kept)

    # ---- internal helpers ----

    @staticmethod
    def _split_blocks(text: str) -> List[str]:
        """Split markdown into logical blocks separated by blank lines."""
        raw = re.split(r"\n{2,}", text.strip())
        return [b.strip() for b in raw if b.strip()]

    @staticmethod
    def _score_block(block: str) -> float:
        """Heuristic quality score for a text block (0-1)."""
        words = block.split()
        if not words:
            return 0.0

        word_count = len(words)
        avg_word_len = sum(len(w) for w in words) / word_count

        # Penalize very short blocks
        length_score = min(word_count / 40.0, 1.0)

        # Penalize blocks that are mostly links
        link_chars = sum(len(m.group()) for m in re.finditer(r"\[.*?\]\(.*?\)", block))
        total_chars = len(block) or 1
        link_density = link_chars / total_chars
        link_score = 1.0 - link_density

        # Reward reasonable average word length (natural prose ≈ 4-8)
        prose_score = 1.0 if 4 <= avg_word_len <= 8 else 0.6

        # Penalize blocks that look like navigation / boilerplate
        boilerplate_patterns = [
            r"^(copyright|©|\||\-\-|all rights reserved)",
            r"^(menu|nav|skip to|jump to|toggle)",
        ]
        boilerplate_penalty = 1.0
        lower = block.lower()
        for pat in boilerplate_patterns:
            if re.search(pat, lower):
                boilerplate_penalty = 0.2
                break

        return length_score * link_score * prose_score * boilerplate_penalty


@dataclass
class BM25ContentFilter(ContentFilterStrategy):
    """Filters content blocks using BM25 relevance scoring against a query."""
    user_query: Optional[str] = None
    bm25_threshold: float = 1.0

    def filter(self, text: str) -> str:
        if not text or not self.user_query:
            return text

        blocks = PruningContentFilter._split_blocks(text)
        query_terms = set(self.user_query.lower().split())

        kept: List[str] = []
        for block in blocks:
            block_lower = block.lower()
            block_terms = set(block_lower.split())
            overlap = len(query_terms & block_terms)
            if overlap > 0:
                score = overlap / (len(query_terms) or 1)
                if score >= self.bm25_threshold or overlap >= 2:
                    kept.append(block)

        return "\n\n".join(kept) if kept else text
