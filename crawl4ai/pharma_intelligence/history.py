"""Cross-run coverage history: avoid resurfacing previously covered news.

The in-run :class:`Deduplicator` only merges articles *within* a single brief.
Client feedback showed the same molecule resurfacing weeks later with no new
development (Retatrutide was covered on 8 June and reappeared on 23 July), so a
brief must also be checked against what has already been published.

Items matching prior coverage are demoted into "Other News" rather than dropped,
so a genuine follow-up development is never silently lost.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# How far back to look for prior coverage of the same story.
HISTORY_LOOKBACK_DAYS = 30

# Title overlap above which two headlines are considered the same story.
TITLE_SIMILARITY_THRESHOLD = 0.55

# Generic pharma-news words carry no discriminating power, so they are ignored
# when comparing headlines (otherwise every approval headline looks alike).
_STOPWORDS = {
    "a", "an", "and", "the", "for", "of", "in", "on", "to", "with", "at", "by",
    "as", "its", "it", "is", "are", "was", "were", "be", "been", "from", "after",
    "new", "data", "results", "study", "trial", "patients", "treatment", "therapy",
    "drug", "phase", "reports", "reported", "announces", "announced", "shows",
    "showed", "us", "fda", "ema", "company", "million", "billion",
}


def _words(text: str) -> Set[str]:
    tokens = re.sub(r"\W+", " ", str(text or "").lower()).split()
    return {t for t in tokens if t and t not in _STOPWORDS and len(t) > 2}


def _similarity(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _molecule_of(item: Dict[str, Any]) -> str:
    entities = item.get("entities") or {}
    if isinstance(entities, dict) and entities.get("molecule"):
        return _norm(entities.get("molecule"))
    return _norm(item.get("molecule"))


def _category_of(item: Dict[str, Any]) -> str:
    return _norm(item.get("primary_category"))


def _url_of(item: Dict[str, Any]) -> str:
    return _norm(item.get("url"))


@dataclass
class HistoryEntry:
    date_key: str
    title: str
    words: Set[str]
    molecule: str
    category: str
    url: str


@dataclass
class CoverageHistory:
    """Index of previously published brief items, keyed for fast comparison."""

    entries: List[HistoryEntry] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.entries)

    @classmethod
    def from_reports(cls, reports: List[Tuple[str, Dict[str, Any]]]) -> "CoverageHistory":
        """Build the index from ``(date_key, stored_report)`` pairs."""
        entries: List[HistoryEntry] = []
        for date_key, report in reports:
            if not isinstance(report, dict):
                continue
            items = list(report.get("key_highlights") or []) + list(
                report.get("other_news") or []
            )
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("headline") or item.get("title") or "")
                entries.append(HistoryEntry(
                    date_key=str(date_key),
                    title=title,
                    words=_words(title),
                    molecule=_molecule_of(item),
                    category=_category_of(item),
                    url=_url_of(item),
                ))
        return cls(entries=entries)

    def find_previous_coverage(self, item: Dict[str, Any]) -> Optional[HistoryEntry]:
        """Return the prior entry covering this item, or None.

        Matching is intentionally conservative-to-moderate: because a match only
        demotes (never drops), a false positive costs ranking, not coverage.
        """
        url = _url_of(item)
        molecule = _molecule_of(item)
        category = _category_of(item)
        title_words = _words(item.get("headline") or item.get("title") or "")

        for entry in self.entries:
            # 1. Same source article → unambiguously the same news.
            if url and entry.url and url == entry.url:
                return entry
            # 2. Same molecule plus either a near-identical headline or the same
            #    event category (i.e. no new milestone type to justify re-running).
            if molecule and entry.molecule and molecule == entry.molecule:
                if _similarity(title_words, entry.words) >= TITLE_SIMILARITY_THRESHOLD:
                    return entry
                if category and entry.category and category == entry.category:
                    return entry
            # 3. No molecule (deals/corporate): fall back to headline similarity.
            elif not molecule and title_words and _similarity(title_words, entry.words) >= 0.7:
                return entry
        return None
