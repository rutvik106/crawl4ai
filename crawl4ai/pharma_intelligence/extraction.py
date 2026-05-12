"""
Layer 1: Pharma Entity Extraction

Extracts structured entities (molecule, company, indication, event type, etc.)
from raw article text using LLM with rule-based fallbacks.
"""
from __future__ import annotations
import json
import re
from typing import Any, Callable, Dict, Optional

from .prompts import SYSTEM_PHARMA_EXPERT, EXTRACTION_PROMPT
from .ontology import REGULATORY_BODIES, THERAPY_AREAS


class EntityExtractor:
    """
    Extracts pharma entities from article title + text.

    Args:
        llm_client: Callable that accepts (system_prompt, user_prompt) -> str.
                    If None, falls back to rule-based heuristics only.
    """

    def __init__(self, llm_client: Optional[Callable[[str, str], str]] = None):
        self.llm_client = llm_client
        self._regulatory_pattern = re.compile(
            r"\b(" + "|".join(REGULATORY_BODIES) + r")\b", re.IGNORECASE
        )
        self._phase_pattern = re.compile(
            r"\bphase\s+(i{1,3}|[1-4]|iv)\b", re.IGNORECASE
        )
        self._event_patterns = [
            (re.compile(r"\b(?:approv|cleared|granted approval)", re.I), "approval"),
            (re.compile(r"\b(?:acqui|merger|takeover|buyout)", re.I), "ma"),
            (re.compile(r"\b(?:licens|partner|collaborat|deal)", re.I), "licensing"),
            (re.compile(r"\b(?:discontinu|halt|terminat|withdraw)", re.I), "discontinuation"),
            (re.compile(r"\b(?:phase\s+(?:iii|3).*(?:met|success|positive|miss|fail))", re.I), "clinical_outcome"),
            (re.compile(r"\b(?:orphan|fast track|breakthrough therapy)", re.I), "designation"),
            (re.compile(r"\b(?:generic|biosimilar).*(?:launch|approv)", re.I), "generic_launch"),
            (re.compile(r"\b(?:patent.*expir|exclusivity.*end)", re.I), "patent"),
            (re.compile(r"\b(?:manufactur|plant|facility|capacity)", re.I), "manufacturing"),
            (re.compile(r"\b(?:preclinical|animal.*study|in vitro)", re.I), "preclinical"),
            (re.compile(r"\b(?:conference|congress|symposium|abstract)", re.I), "conference"),
        ]

    def extract(self, title: str, text: str) -> Dict[str, Any]:
        """
        Extract pharma entities from article.
        Returns a dict with keys: molecule, brand_name, company, indication,
        trial_phase, geography, regulatory_body, event_type, deal_value.
        """
        if self.llm_client:
            return self._extract_with_llm(title, text)
        return self._extract_with_rules(title, text)

    def _extract_with_llm(self, title: str, text: str) -> Dict[str, Any]:
        truncated = text[:3000] if len(text) > 3000 else text
        user_prompt = EXTRACTION_PROMPT.format(title=title, text=truncated)
        try:
            response = self.llm_client(SYSTEM_PHARMA_EXPERT, user_prompt)
            data = _parse_json(response)
            return self._normalise(data)
        except Exception:
            return self._extract_with_rules(title, text)

    def _extract_with_rules(self, title: str, text: str) -> Dict[str, Any]:
        combined = f"{title} {text[:1500]}"

        # Regulatory body
        reg_match = self._regulatory_pattern.search(combined)
        regulatory_body = reg_match.group(0).upper() if reg_match else None

        # Trial phase
        phase_match = self._phase_pattern.search(combined)
        trial_phase = None
        if phase_match:
            raw = phase_match.group(1).upper()
            mapping = {"I": "Phase I", "II": "Phase II", "III": "Phase III",
                       "IV": "Phase IV", "1": "Phase I", "2": "Phase II",
                       "3": "Phase III", "4": "Phase IV"}
            trial_phase = mapping.get(raw)

        # Event type (first match wins)
        event_type = "other"
        for pattern, etype in self._event_patterns:
            if pattern.search(combined):
                event_type = etype
                break

        return {
            "molecule": None,
            "brand_name": None,
            "company": None,
            "indication": None,
            "trial_phase": trial_phase,
            "geography": None,
            "regulatory_body": regulatory_body,
            "event_type": event_type,
            "deal_value": None,
        }

    def _normalise(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure all expected keys are present with sensible defaults."""
        defaults = {
            "molecule": None, "brand_name": None, "company": None,
            "indication": None, "trial_phase": None, "geography": None,
            "regulatory_body": None, "event_type": "other", "deal_value": None,
        }
        defaults.update({k: v for k, v in data.items() if v not in ("", "null")})
        return defaults


def _parse_json(text: str) -> Dict[str, Any]:
    """Extract and parse the first JSON object found in LLM response text."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start:end + 1])
    raise ValueError(f"No JSON object found in response: {text[:200]}")
