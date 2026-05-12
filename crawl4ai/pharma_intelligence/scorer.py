"""
Layer 4: KPI-Weighted Relevance Scoring

Scores each article 0-100 based on business impact, therapy importance,
Indian market relevance, novelty, and regulatory significance.

Design: hybrid approach — LLM provides nuanced scoring when available,
rule-based KPI weights provide a reliable fallback.
"""
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional

from .ontology import KPI_WEIGHTS, KEY_HIGHLIGHT_CATEGORIES, KEY_HIGHLIGHT_THERAPY_AREAS, KEY_HIGHLIGHT_SCORE_THRESHOLD
from .prompts import SYSTEM_PHARMA_EXPERT, RELEVANCE_PROMPT
from .extraction import _parse_json


class RelevanceScorer:
    """
    Scores pharma articles on a 0-100 scale for strategic relevance.
    Scores >= KEY_HIGHLIGHT_SCORE_THRESHOLD qualify as Key Highlights.
    """

    def __init__(self, llm_client: Optional[Callable[[str, str], str]] = None):
        self.llm_client = llm_client

    def score(
        self,
        title: str,
        categories: List[str],
        entities: Dict[str, Any],
        event_type: str = "other",
    ) -> Dict[str, Any]:
        """
        Returns dict with: total_score (0-100), breakdown (dict), score_rationale (str),
        is_key_highlight (bool).
        """
        if self.llm_client:
            result = self._score_with_llm(title, categories, entities, event_type)
        else:
            result = self._score_with_rules(categories, entities, event_type)

        result["is_key_highlight"] = self._determine_key_highlight(
            result["total_score"], categories
        )
        return result

    def _score_with_llm(self, title: str, categories: List[str], entities: Dict, event_type: str) -> Dict:
        cats_str = ", ".join(categories)
        entities_str = ", ".join(f"{k}: {v}" for k, v in entities.items() if v)
        user_prompt = RELEVANCE_PROMPT.format(
            title=title, categories=cats_str,
            entities=entities_str, event_type=event_type
        )
        try:
            response = self.llm_client(SYSTEM_PHARMA_EXPERT, user_prompt)
            data = _parse_json(response)
            total = int(data.get("total_score", 0))
            total = max(0, min(100, total))  # clamp to 0-100
            return {
                "total_score": total,
                "breakdown": data.get("breakdown", {}),
                "score_rationale": data.get("score_rationale", ""),
            }
        except Exception:
            return self._score_with_rules(categories, entities, event_type)

    def _score_with_rules(self, categories: List[str], entities: Dict, event_type: str) -> Dict:
        # KPI weight contributes up to 40 points
        kpi_weight = KPI_WEIGHTS.get(event_type, 2)
        kpi_score = int((kpi_weight / 10) * 40)

        # Category signals contribute up to 40 points
        cat_score = 0
        high_value_cats = {
            "FDA Approval": 40, "EMA Approval": 38, "CDSCO Approval": 36,
            "Phase III Success": 35, "Phase III Failure": 28,
            "M&A Activity": 30, "Licensing Deal": 28,
            "Orphan Drug Designation": 25, "Fast Track Designation": 22,
            "Breakthrough Therapy": 25, "First Generic Launch": 22,
            "Patent Expiry": 30, "Label Expansion": 20,
            "Gene Therapy": 20, "Biosimilar": 18,
        }
        for cat in categories:
            cat_score = max(cat_score, high_value_cats.get(cat, 0))
        cat_score = min(40, cat_score)

        # Indian market bonus (up to 20 points)
        indian_score = 20 if "Indian Market" in categories else 5

        total = kpi_score + cat_score + indian_score
        total = max(0, min(100, total))

        return {
            "total_score": total,
            "breakdown": {
                "kpi_weight": kpi_score,
                "category_value": cat_score,
                "indian_market": indian_score,
            },
            "score_rationale": f"Rule-based: KPI={kpi_weight}/10, event_type={event_type}",
        }

    @staticmethod
    def _determine_key_highlight(score: int, categories: List[str]) -> bool:
        """Promotes to Key Highlight if score threshold met OR high-impact category present."""
        if score >= KEY_HIGHLIGHT_SCORE_THRESHOLD:
            return True
        # Override for certain always-important categories
        always_highlight = {"Gene Therapy", "Orphan Drug Designation",
                            "First Generic Launch", "FDA Approval",
                            "EMA Approval", "CDSCO Approval"}
        return bool(set(categories) & always_highlight)
