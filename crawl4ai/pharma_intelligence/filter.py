"""
Layer 3: Exclusion Filter / Noise Reduction

Two-stage filtering:
1. Rule-based hard exclusion (fast, zero LLM cost)
2. AI-assisted exclusion for ambiguous cases

This layer is the primary noise reduction mechanism. The spec
identifies that ~70% of crawled articles are not useful.
"""
from __future__ import annotations
from typing import Any, Callable, Dict, Optional, Tuple

from .ontology import is_hard_excluded, has_strong_include_signal
from .prompts import SYSTEM_PHARMA_EXPERT, EXCLUSION_PROMPT
from .extraction import _parse_json


class ExclusionFilter:
    """
    Determines whether a pharma article should be included or excluded
    from the final intelligence brief.

    Logic:
    - Strong include signal → include immediately (skip AI check)
    - Hard exclusion pattern → exclude immediately (skip AI check)
    - Ambiguous → call LLM for a decision
    - No LLM available → default to include (conservative)
    """

    def __init__(self, llm_client: Optional[Callable[[str, str], str]] = None):
        self.llm_client = llm_client

    def should_exclude(
        self,
        title: str,
        text: str,
        event_type: str = "other",
    ) -> Tuple[bool, str]:
        """
        Returns (exclude: bool, reason: str).
        exclude=True means the article should be filtered out.
        """
        combined = f"{title} {text[:1000]}"

        # Stage 1a: Strong include signal overrides everything
        if has_strong_include_signal(combined):
            return False, "Strong include signal detected (approval/Phase III/M&A/designation)"

        # Stage 1b: Hard pattern exclusion
        if is_hard_excluded(combined):
            return True, "Matched hard exclusion pattern (IND/CTA/preclinical/conference/Phase I-II)"

        # Exclude zero-KPI event types immediately
        zero_kpi_types = {"ind_approval", "cta_approval", "filing_acceptance",
                          "priority_review", "trial_initiation", "conference",
                          "preclinical"}
        if event_type in zero_kpi_types:
            return True, f"Zero-KPI event type: {event_type}"

        # Stage 2: AI-assisted exclusion for ambiguous cases
        if self.llm_client:
            return self._ai_exclude(title, text, event_type)

        # No LLM: conservative default is include
        return False, "No LLM available; defaulting to include"

    def _ai_exclude(self, title: str, text: str, event_type: str) -> Tuple[bool, str]:
        truncated = text[:2000] if len(text) > 2000 else text
        user_prompt = EXCLUSION_PROMPT.format(
            title=title, text=truncated, event_type=event_type
        )
        try:
            response = self.llm_client(SYSTEM_PHARMA_EXPERT, user_prompt)
            data = _parse_json(response)
            exclude = bool(data.get("exclude", False))
            reason = data.get("reason", "AI decision")
            confidence = float(data.get("confidence", 0.5))
            # Low confidence → err on side of inclusion
            if confidence < 0.65:
                return False, f"Low-confidence AI exclusion ({confidence:.2f}); defaulting to include"
            return exclude, reason
        except Exception as e:
            return False, f"AI exclusion error ({e}); defaulting to include"
