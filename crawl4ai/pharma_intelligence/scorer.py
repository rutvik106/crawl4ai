"""Layer 4: contextual Daily Bites prioritization."""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional

from .extraction import _parse_json
from .ontology import KEY_HIGHLIGHT_SCORE_THRESHOLD, detect_regulatory_status
from .prompts import RELEVANCE_PROMPT, SYSTEM_PHARMA_EXPERT

logger = logging.getLogger(__name__)


class RelevanceScorer:
    """Score strategic relevance without treating a category as an automatic Key.

    All articles remain in the brief. This class only decides whether an item is a
    Key Highlight or Other News and records an auditable rationale.
    """

    def __init__(self, llm_client: Optional[Callable[[str, str], str]] = None):
        self.llm_client = llm_client

    def score(
        self,
        title: str,
        categories: List[str],
        entities: Dict[str, Any],
        event_type: str = "other",
        text: str = "",
    ) -> Dict[str, Any]:
        if self.llm_client:
            result = self._score_with_llm(title, text, categories, entities, event_type)
        else:
            result = self._score_with_rules(title, text, categories, entities, event_type)
        result["is_key_highlight"] = self._determine_key_highlight(
            result, title, text, entities, event_type
        )
        return result

    def _score_with_llm(
        self,
        title: str,
        text: str,
        categories: List[str],
        entities: Dict[str, Any],
        event_type: str,
    ) -> Dict[str, Any]:
        cats_str = ", ".join(categories)
        entities_str = ", ".join(f"{k}: {v}" for k, v in entities.items() if v)
        user_prompt = RELEVANCE_PROMPT.format(
            title=title,
            text=text[:2500],
            categories=cats_str,
            entities=entities_str,
            event_type=event_type,
        )
        try:
            data = _parse_json(self.llm_client(SYSTEM_PHARMA_EXPERT, user_prompt))
            total = max(0, min(100, int(data.get("total_score", 0))))
            return {
                "total_score": total,
                "breakdown": data.get("breakdown", {}),
                "score_rationale": data.get("score_rationale", ""),
                "classification_confidence": self._confidence(data.get("classification_confidence")),
                "model_key_recommendation": bool(data.get("is_key_highlight", False)),
            }
        except Exception as e:
            logger.warning(
                "LLM relevance scoring failed for '%s' (%s: %s); falling back to rule-based scoring",
                title, type(e).__name__, e,
            )
            return self._score_with_rules(title, text, categories, entities, event_type)

    def _score_with_rules(
        self,
        title: str,
        text: str,
        categories: List[str],
        entities: Dict[str, Any],
        event_type: str,
    ) -> Dict[str, Any]:
        combined = f"{title} {text[:3000]}".lower()
        status = self._regulatory_status(title, text, entities, event_type)

        maturity_by_status = {
            "final_approval": 30,
            "label_expansion": 27,
            "withdrawal": 27,
            "trial_outcome": 24,
            "positive_recommendation": 18,
            "launch": 18,
            "exclusivity": 18,
            "priority_review": 10,
            "designation": 10,
            "filing_acceptance": 6,
            "not_applicable": 0,
        }
        maturity = maturity_by_status.get(status, 0)
        if not maturity:
            maturity = {
                "ma": 24,
                "licensing": 20,
                "clinical_outcome": 24,
                "generic_launch": 18,
                "manufacturing": 10,
                "patent": 22,
                "discontinuation": 24,
            }.get(event_type, 5)
        market_shift = bool(re.search(
            r"\b(?:price war|market slowdown|market momentum slows|prescription plateau|"
            r"sales targets?|inventory build[- ]?up|market disruption)\b", combined
        ))
        if market_shift:
            maturity = max(maturity, 24)

        evidence = 0
        if re.search(r"\b(?:phase\s*(?:(?:ii(?:b)?\s*/\s*)?iii|3)|pivotal)\b", combined):
            evidence = 16
        elif re.search(r"\bphase\s*(?:ii|2)\b", combined):
            evidence = 8
        elif re.search(r"\b(?:phase\s*(?:i|1)|preclinical|early[- ]stage)\b", combined):
            evidence = 2
        if re.search(r"\b(?:met (?:the )?primary endpoint|reduction|improvement|response(?: rate)?|pfs|os)\b", combined) and re.search(r"\d", combined):
            evidence = max(evidence, 20)
        elif re.search(r"(?:\d+(?:\.\d+)?%|\$[\d,.]+|₹[\d,.]+|\b\d+ patients?\b)", combined):
            evidence = max(evidence, 6)

        strategic = 0
        strategic_signals = (
            r"\bfirst(?:[- ]in[- ]class| and only| therapy| treatment| oral| generic| in )",
            r"\bonly\b.{0,30}\b(?:therapy|treatment|inhibitor|option)",
            r"\bstandard of care\b|\bpractice[- ]changing\b",
            r"\bunmet need\b|\bno (?:approved|available) (?:therapy|treatment)",
        )
        strategic += min(16, sum(8 for pattern in strategic_signals if re.search(pattern, combined)))
        if status in {"label_expansion", "withdrawal"} or re.search(
            r"new (?:indication|population|patient population)|expan(?:d|ding|ded)s? "
            r"(?:the |its )?(?:indication|patient population)|beyond adults|"
            r"safety concern|benefit.?risk",
            combined,
        ):
            strategic += 8
        if market_shift:
            strategic += 12
        if re.search(r"\borphan drug\b", combined) and re.search(r"\bfast track\b", combined):
            strategic += 8
        if set(categories) & {"Gene Therapy", "Rare Disease", "Oncology", "GLP-1 / Obesity"}:
            strategic += 4
        strategic = min(20, strategic)

        commercial = 0
        if entities.get("deal_value") or re.search(r"(?:\$|usd\s*)[\d,.]+\s*(?:billion|million|bn|mn|b|m)\b", combined):
            commercial = 12
        if re.search(r"\b(?:launch|market entry|new market|commerciali[sz]|sales|pricing|price war|patent expir|exclusivity|market share)\b", combined):
            commercial = max(commercial, 8)
        if re.search(r"\b(?:blockbuster|portfolio transformation|revenue of|peak sales)\b", combined):
            commercial = max(commercial, 15)
        if market_shift:
            commercial = 15

        india = 0
        if re.search(r"\b(?:india|cdsco|torrent pharma)\b", combined):
            india = 15
        elif re.search(r"\b(?:zydus|sun pharma|cipla|dr\.? reddy|lupin|biocon|glenmark|alembic|aurobindo)\b", combined):
            india = 8

        breakdown = {
            "event_maturity": maturity,
            "evidence_strength": evidence,
            "strategic_significance": strategic,
            "commercial_implications": commercial,
            "india_torrent_relevance": india,
        }
        total = max(0, min(100, sum(breakdown.values())))
        strongest = max(breakdown, key=breakdown.get)
        rationale = (
            f"{status.replace('_', ' ')}; strongest factor is "
            f"{strongest.replace('_', ' ')} ({breakdown[strongest]} points)."
        )
        return {
            "total_score": total,
            "breakdown": breakdown,
            "score_rationale": rationale,
            "classification_confidence": 0.7,
            "model_key_recommendation": total >= KEY_HIGHLIGHT_SCORE_THRESHOLD,
        }

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5

    @staticmethod
    def _regulatory_status(
        title: str, text: str, entities: Dict[str, Any], event_type: str
    ) -> str:
        supplied = entities.get("regulatory_status")
        if supplied and supplied != "not_applicable":
            return str(supplied)
        return detect_regulatory_status(title, text, event_type, truncate=1800)

    def _determine_key_highlight(
        self,
        result: Dict[str, Any],
        title: str,
        text: str,
        entities: Dict[str, Any],
        event_type: str,
    ) -> bool:
        score = int(result.get("total_score", 0))
        combined = f"{title} {text[:2500]}".lower()
        headline = title.lower()
        status = self._regulatory_status(title, text, entities, event_type)

        # Scoped to the HEADLINE (not the full body) so a market-commentary
        # article that merely mentions "generic" in passing (e.g. "Generic
        # semaglutide launched post-patent expiry" inside a piece about a
        # broader market slowdown) isn't wrongly force-demoted. Genuine
        # routine-generic-approval articles state it in the headline itself
        # (e.g. "Alembic receives FDA final approval for generic oseltamivir").
        routine_generic = bool(re.search(r"\b(?:generic|anda|tentative approval)\b", headline))
        exceptional_generic = bool(re.search(r"\b(?:first generic|exclusive|exclusivity|market size|annual sales)\b", combined))
        if routine_generic and not exceptional_generic:
            return False

        early_transaction = event_type in {"ma", "licensing"} and bool(
            re.search(r"\b(?:preclinical|early[- ]stage|discovery stage)\b", combined)
        )
        if early_transaction:
            return False

        immature = {"priority_review", "filing_acceptance", "designation"}
        if status in immature:
            breakdown = result.get("breakdown", {})
            return bool(
                score >= 50
                and int(breakdown.get("evidence_strength", 0)) >= 14
                and int(breakdown.get("strategic_significance", 0)) >= 12
                and int(breakdown.get("india_torrent_relevance", 0)) >= 8
            )

        return score >= KEY_HIGHLIGHT_SCORE_THRESHOLD
