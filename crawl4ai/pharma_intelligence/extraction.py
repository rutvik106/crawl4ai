"""
Layer 1: Pharma Entity Extraction

Extracts structured entities (molecule, company, indication, event type, etc.)
from raw article text using LLM with rule-based fallbacks.
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any, Callable, Dict, Optional

from .prompts import SYSTEM_PHARMA_EXPERT, EXTRACTION_PROMPT
from .ontology import REGULATORY_BODIES, THERAPY_AREAS, detect_regulatory_status

logger = logging.getLogger(__name__)


class EntityExtractor:
    def __init__(self, llm_client: Optional[Callable[[str, str], str]] = None):
        self.llm_client = llm_client
        self._regulatory_pattern = re.compile(
            r"\b(" + "|".join(REGULATORY_BODIES) + r")\b", re.IGNORECASE
        )
        self._phase_pattern = re.compile(
            r"\bphase\s+(i{1,3}|[1-4]|iv)\b", re.IGNORECASE
        )
        self._event_patterns = [
            # Specific milestones must precede the broad approval pattern. News
            # about Priority Review often mentions an older approval in its body.
            (re.compile(r"\b(?:label (?:update|expansion)|new indication)", re.I), "label_expansion"),
            (re.compile(r"\b(?:priority review|filing.{0,30}accept|nda.{0,30}accept)", re.I), "designation"),
            (re.compile(r"\b(?:orphan|fast track|breakthrough therapy)", re.I), "designation"),
            (re.compile(r"\b(?:phase\s+(?:(?:ii(?:b)?\s*/\s*)?iii|3).*(?:met|show|success|positive|miss|fail|reduc))", re.I), "clinical_outcome"),
            (re.compile(r"\b(?:acqui|merger|takeover|buyout)", re.I), "ma"),
            (re.compile(r"\b(?:licens|partner|collaborat|deal)", re.I), "licensing"),
            (re.compile(r"\b(?:discontinu|halt|terminat|withdraw)", re.I), "discontinuation"),
            (re.compile(r"\b(?:generic|biosimilar).*(?:launch|approv)", re.I), "generic_launch"),
            (re.compile(r"\b(?:patent.*expir|exclusivity.*end)", re.I), "patent"),
            (re.compile(r"\b(?:manufactur|plant|facility|capacity)", re.I), "manufacturing"),
            (re.compile(r"\b(?:preclinical|animal.*study|in vitro)", re.I), "preclinical"),
            (re.compile(r"\b(?:conference|congress|symposium|abstract)", re.I), "conference"),
            (re.compile(r"\b(?:approv|cleared|granted approval|marketing authori[sz]ation)", re.I), "approval"),
        ]

    def extract(self, title: str, text: str) -> Dict[str, Any]:
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
        except Exception as e:
            logger.warning(
                "LLM extraction failed for '%s' (%s: %s); falling back to rule-based extraction",
                title, type(e).__name__, e,
            )
            return self._extract_with_rules(title, text)

    def _extract_with_rules(self, title: str, text: str) -> Dict[str, Any]:
        combined = f"{title} {text[:1500]}"
        reg_match = self._regulatory_pattern.search(combined)
        regulatory_body = reg_match.group(0).upper() if reg_match else None
        phase_match = self._phase_pattern.search(combined)
        trial_phase = None
        if re.search(r"\bphase\s+ii(?:b)?\s*/\s*iii\b", combined, re.I):
            trial_phase = "Phase III"
        elif phase_match:
            raw = phase_match.group(1).upper()
            mapping = {"I": "Phase I", "II": "Phase II", "III": "Phase III",
                       "IV": "Phase IV", "1": "Phase I", "2": "Phase II",
                       "3": "Phase III", "4": "Phase IV"}
            trial_phase = mapping.get(raw)
        event_type = "other"
        for pattern, etype in self._event_patterns:
            if pattern.search(combined):
                event_type = etype
                break
        transaction_type = None
        if re.search(r"\b(?:acqui(?:re[sd]?|sition)|merger|takeover|buyout)\b", combined, re.I):
            transaction_type = "Acquisition"
        elif re.search(r"\blicens(?:e|ed|ing|ure)\b", combined, re.I):
            transaction_type = "Licensing"
        elif re.search(r"\bcollaborat(?:e[sd]?|ion|ive)\b", combined, re.I):
            transaction_type = "Collaboration"
        elif re.search(r"\bpartner(?:ship|ed|s|ing)?\b", combined, re.I):
            transaction_type = "Partnership"
        return {
            "molecule": None, "brand_name": None, "company": None,
            "counterparties": [], "transaction_type": transaction_type,
            "indication": None, "trial_phase": trial_phase, "geography": None,
            "regulatory_body": regulatory_body, "event_type": event_type,
            "regulatory_status": detect_regulatory_status(title, text, event_type, truncate=1500),
            "deal_value": None,
        }

    def _normalise(self, data: Dict[str, Any]) -> Dict[str, Any]:
        defaults = {
            "molecule": None, "brand_name": None, "company": None,
            "counterparties": [], "transaction_type": None,
            "indication": None, "trial_phase": None, "geography": None,
            "regulatory_body": None, "event_type": "other",
            "regulatory_status": "not_applicable", "deal_value": None,
        }
        defaults.update({k: v for k, v in data.items() if v not in ("", "null")})
        return defaults


def _parse_json(text: str) -> Dict[str, Any]:
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start:end + 1])
    raise ValueError(f"No JSON object found in response: {text[:200]}")
