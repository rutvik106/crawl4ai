"""
Layer 4: KPI-Weighted Relevance Scoring
"""
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional

from .ontology import KPI_WEIGHTS, KEY_HIGHLIGHT_CATEGORIES, KEY_HIGHLIGHT_SCORE_THRESHOLD
from .prompts import SYSTEM_PHARMA_EXPERT, RELEVANCE_PROMPT
from .extraction import _parse_json


class RelevanceScorer:
    def __init__(self, llm_client: Optional[Callable[[str, str], str]] = None):
        self.llm_client = llm_client

    def score(self, title: str, categories: List[str], entities: Dict[str, Any], event_type: str = "other") -> Dict[str, Any]:
        if self.llm_client:
            result = self._score_with_llm(title, categories, entities, event_type)
        else:
            result = self._score_with_rules(categories, entities, event_type)
        result["is_key_highlight"] = self._determine_key_highlight(result["total_score"], categories)
        return result

    def _score_with_llm(self, title: str, categories: List[str], entities: Dict, event_type: str) -> Dict:
        cats_str = ", ".join(categories)
        entities_str = ", ".join(f"{k}: {v}" for k, v in entities.items() if v)
        user_prompt = RELEVANCE_PROMPT.format(
            title=title, categories=cats_str, entities=entities_str, event_type=event_type
        )
        try:
            response = self.llm_client(SYSTEM_PHARMA_EXPERT, user_prompt)
            data = _parse_json(response)
            total = max(0, min(100, int(data.get("total_score", 0))))
            return {
                "total_score": total,
                "breakdown": data.get("breakdown", {}),
                "score_rationale": data.get("score_rationale", ""),
            }
        except Exception:
            return self._score_with_rules(categories, entities, event_type)

    def _score_with_rules(self, categories: List[str], entities: Dict, event_type: str) -> Dict:
        kpi_weight = KPI_WEIGHTS.get(event_type, 2)
        kpi_score = int((kpi_weight / 10) * 40)
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
        indian_score = 20 if "Indian Market" in categories else 5
        total = max(0, min(100, kpi_score + cat_score + indian_score))
        return {
            "total_score": total,
            "breakdown": {"kpi_weight": kpi_score, "category_value": cat_score, "indian_market": indian_score},
            "score_rationale": f"Rule-based: KPI={kpi_weight}/10, event_type={event_type}",
        }

    @staticmethod
    def _determine_key_highlight(score: int, categories: List[str]) -> bool:
        if score >= KEY_HIGHLIGHT_SCORE_THRESHOLD:
            return True
        always_highlight = {"Gene Therapy", "Orphan Drug Designation", "First Generic Launch",
                            "FDA Approval", "EMA Approval", "CDSCO Approval"}
        return bool(set(categories) & always_highlight)
