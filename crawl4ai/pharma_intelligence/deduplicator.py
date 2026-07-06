"""
Duplicate Event Clustering
"""
from __future__ import annotations
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from .prompts import SYSTEM_PHARMA_EXPERT, DEDUPLICATION_PROMPT
from .extraction import _parse_json

logger = logging.getLogger(__name__)


def _normalise_text(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _entity_fingerprint(entities: Dict[str, Any]) -> str:
    parts = [
        str(entities.get("molecule", "") or ""),
        str(entities.get("event_type", "") or ""),
        str(entities.get("regulatory_body", "") or ""),
        str(entities.get("company", "") or ""),
    ]
    return "|".join(p.lower().strip() for p in parts)


def _jaccard_title(a: str, b: str) -> float:
    words_a = set(_normalise_text(a).split())
    words_b = set(_normalise_text(b).split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


class Deduplicator:
    JACCARD_THRESHOLD = 0.55
    ENTITY_MATCH_THRESHOLD = 2

    def __init__(self, llm_client: Optional[Callable[[str, str], str]] = None):
        self.llm_client = llm_client

    def cluster(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if len(articles) <= 1:
            return articles
        clusters: List[List[int]] = []
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
        if _jaccard_title(a.get("title", ""), b.get("title", "")) >= self.JACCARD_THRESHOLD:
            return True
        fp_a = _entity_fingerprint(a.get("entities", {}))
        fp_b = _entity_fingerprint(b.get("entities", {}))
        matches = sum(1 for x, y in zip(fp_a.split("|"), fp_b.split("|")) if x and y and x == y)
        if matches >= self.ENTITY_MATCH_THRESHOLD:
            if self.llm_client:
                return self._ai_verify_duplicate(a, b)
            return True
        return False

    def _ai_verify_duplicate(self, a: Dict, b: Dict) -> bool:
        entities_a = ", ".join(f"{k}: {v}" for k, v in a.get("entities", {}).items() if v)
        entities_b = ", ".join(f"{k}: {v}" for k, v in b.get("entities", {}).items() if v)
        user_prompt = DEDUPLICATION_PROMPT.format(
            title_a=a.get("title", ""), summary_a=a.get("summary", "")[:400], entities_a=entities_a,
            title_b=b.get("title", ""), summary_b=b.get("summary", "")[:400], entities_b=entities_b,
        )
        try:
            response = self.llm_client(SYSTEM_PHARMA_EXPERT, user_prompt)
            return bool(_parse_json(response).get("is_duplicate", False))
        except Exception as e:
            logger.warning(
                "LLM dedup check failed for '%s' / '%s' (%s: %s); defaulting to not-duplicate",
                a.get("title", ""), b.get("title", ""), type(e).__name__, e,
            )
            return False

    @staticmethod
    def _merge_cluster(articles: List[Dict]) -> Dict:
        if len(articles) == 1:
            result = articles[0].copy()
            result["sources"] = [articles[0].get("source", "")]
            result["is_consolidated"] = False
            return result
        def richness(a: Dict) -> int:
            return sum(1 for v in a.get("entities", {}).values() if v) * 100 + len(a.get("summary", ""))
        primary = max(articles, key=richness)
        result = primary.copy()
        result["sources"] = list({a.get("source", "") for a in articles if a.get("source")})
        result["is_consolidated"] = True
        result["source_count"] = len(articles)
        return result
