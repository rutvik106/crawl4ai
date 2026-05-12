"""
Duplicate Event Clustering

Multiple sources often report the same FDA approval, M&A deal, or
Phase III result. This module clusters duplicate articles into single
events, preserving the richer content from each source.

Design: two-pass approach:
1. Exact/fuzzy entity matching (cheap, catches most duplicates)
2. AI verification for uncertain cases
"""
from __future__ import annotations
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .prompts import SYSTEM_PHARMA_EXPERT, DEDUPLICATION_PROMPT
from .extraction import _parse_json


def _normalise_text(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _entity_fingerprint(entities: Dict[str, Any]) -> str:
    """Creates a short fingerprint of key entities for fast comparison."""
    parts = [
        str(entities.get("molecule", "") or ""),
        str(entities.get("event_type", "") or ""),
        str(entities.get("regulatory_body", "") or ""),
        str(entities.get("company", "") or ""),
    ]
    return "|".join(p.lower().strip() for p in parts)


def _jaccard_title(a: str, b: str) -> float:
    """Jaccard similarity on word sets for quick title comparison."""
    words_a = set(_normalise_text(a).split())
    words_b = set(_normalise_text(b).split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


class Deduplicator:
    """
    Clusters articles that report the same pharma event.

    After deduplication, each cluster is consolidated into a single
    article entry that retains the most complete information.
    """

    JACCARD_THRESHOLD = 0.55  # titles this similar are likely duplicates
    ENTITY_MATCH_THRESHOLD = 2  # fingerprint segments that must match

    def __init__(self, llm_client: Optional[Callable[[str, str], str]] = None):
        self.llm_client = llm_client

    def cluster(
        self,
        articles: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Groups duplicate articles. Returns a list where duplicates are
        merged into a single item with combined sources.

        Each article dict must have: title, summary, entities (dict), url, source.
        Returns same structure with added: sources (list), is_consolidated (bool).
        """
        if len(articles) <= 1:
            return articles

        clusters: List[List[int]] = []  # groups of article indices
        assigned: List[bool] = [False] * len(articles)

        for i, art_a in enumerate(articles):
            if assigned[i]:
                continue
            cluster = [i]
            assigned[i] = True
            for j, art_b in enumerate(articles):
                if i >= j or assigned[j]:
                    continue
                if self._are_duplicates(art_a, art_b):
                    cluster.append(j)
                    assigned[j] = True
            clusters.append(cluster)

        return [self._merge_cluster([articles[i] for i in cluster]) for cluster in clusters]

    def _are_duplicates(self, a: Dict, b: Dict) -> bool:
        # Fast check: title similarity
        if _jaccard_title(a.get("title", ""), b.get("title", "")) >= self.JACCARD_THRESHOLD:
            return True

        # Medium check: entity fingerprint overlap
        fp_a = _entity_fingerprint(a.get("entities", {}))
        fp_b = _entity_fingerprint(b.get("entities", {}))
        segments_a = fp_a.split("|")
        segments_b = fp_b.split("|")
        matches = sum(1 for x, y in zip(segments_a, segments_b)
                      if x and y and x == y)
        if matches >= self.ENTITY_MATCH_THRESHOLD:
            if self.llm_client:
                return self._ai_verify_duplicate(a, b)
            return True

        return False

    def _ai_verify_duplicate(self, a: Dict, b: Dict) -> bool:
        entities_a = ", ".join(f"{k}: {v}" for k, v in a.get("entities", {}).items() if v)
        entities_b = ", ".join(f"{k}: {v}" for k, v in b.get("entities", {}).items() if v)
        user_prompt = DEDUPLICATION_PROMPT.format(
            title_a=a.get("title", ""),
            summary_a=a.get("summary", "")[:400],
            entities_a=entities_a,
            title_b=b.get("title", ""),
            summary_b=b.get("summary", "")[:400],
            entities_b=entities_b,
        )
        try:
            response = self.llm_client(SYSTEM_PHARMA_EXPERT, user_prompt)
            data = _parse_json(response)
            return bool(data.get("is_duplicate", False))
        except Exception:
            return False

    @staticmethod
    def _merge_cluster(articles: List[Dict]) -> Dict:
        """Merges a cluster into the richest single article."""
        if len(articles) == 1:
            result = articles[0].copy()
            result["sources"] = [articles[0].get("source", "")]
            result["is_consolidated"] = False
            return result

        # Richest article: longest summary + most entities
        def richness(a: Dict) -> int:
            ents = sum(1 for v in a.get("entities", {}).values() if v)
            summ = len(a.get("summary", ""))
            return ents * 100 + summ

        primary = max(articles, key=richness)
        result = primary.copy()
        result["sources"] = list({a.get("source", "") for a in articles if a.get("source")})
        result["is_consolidated"] = True
        result["source_count"] = len(articles)
        return result
