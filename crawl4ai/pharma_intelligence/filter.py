"""
Layer 3: Exclusion Filter / Noise Reduction
"""
from __future__ import annotations
from typing import Callable, Optional, Tuple

from .ontology import is_hard_excluded, has_strong_include_signal
from .prompts import SYSTEM_PHARMA_EXPERT, EXCLUSION_PROMPT
from .extraction import _parse_json


class ExclusionFilter:
    def __init__(self, llm_client: Optional[Callable[[str, str], str]] = None):
        self.llm_client = llm_client

    def should_exclude(self, title: str, text: str, event_type: str = "other") -> Tuple[bool, str]:
        combined = f"{title} {text[:1000]}"
        if has_strong_include_signal(combined):
            return False, "Strong include signal detected (approval/Phase III/M&A/designation)"
        if is_hard_excluded(combined):
            return True, "Matched hard exclusion pattern (IND/CTA/preclinical/conference/Phase I-II)"
        zero_kpi_types = {"ind_approval", "cta_approval", "filing_acceptance",
                          "trial_initiation", "conference", "preclinical"}
        if event_type in zero_kpi_types:
            return True, f"Zero-KPI event type: {event_type}"
        if self.llm_client:
            return self._ai_exclude(title, text, event_type)
        return False, "No LLM available; defaulting to include"

    def _ai_exclude(self, title: str, text: str, event_type: str) -> Tuple[bool, str]:
        truncated = text[:2000] if len(text) > 2000 else text
        user_prompt = EXCLUSION_PROMPT.format(title=title, text=truncated, event_type=event_type)
        try:
            response = self.llm_client(SYSTEM_PHARMA_EXPERT, user_prompt)
            data = _parse_json(response)
            exclude = bool(data.get("exclude", False))
            reason = data.get("reason", "AI decision")
            confidence = float(data.get("confidence", 0.5))
            if confidence < 0.65:
                return False, f"Low-confidence AI exclusion ({confidence:.2f}); defaulting to include"
            return exclude, reason
        except Exception as e:
            return False, f"AI exclusion error ({e}); defaulting to include"
