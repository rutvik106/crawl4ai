"""
Layer 5: Leadership-Ready Summarization
"""
from __future__ import annotations
import logging
import re
from typing import Any, Callable, Dict, Optional

from .prompts import SYSTEM_PHARMA_EXPERT, SUMMARIZATION_PROMPT
from .extraction import _parse_json

logger = logging.getLogger(__name__)


class LeadershipSummarizer:
    def __init__(self, llm_client: Optional[Callable[[str, str], str]] = None):
        self.llm_client = llm_client

    def summarize(self, title: str, text: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        if self.llm_client:
            return self._summarize_with_llm(title, text, entities)
        return self._summarize_with_rules(title, text, entities)

    def _summarize_with_llm(self, title: str, text: str, entities: Dict) -> Dict:
        truncated = text[:3500] if len(text) > 3500 else text
        user_prompt = SUMMARIZATION_PROMPT.format(
            title=title, text=truncated,
            molecule=entities.get("molecule") or "N/A",
            company=entities.get("company") or "N/A",
            indication=entities.get("indication") or "N/A",
            event_type=entities.get("event_type") or "N/A",
        )
        try:
            response = self.llm_client(SYSTEM_PHARMA_EXPERT, user_prompt)
            data = _parse_json(response)
            key_points = data.get("key_points") or []
            if not isinstance(key_points, list):
                key_points = [str(key_points)]
            key_points = [str(p).strip() for p in key_points if str(p).strip()]
            fallbacks = self._derive_components(text, entities)
            return {
                "summary": data.get("summary") or self._extract_lead_sentences(text),
                "headline": data.get("headline", title[:80]),
                "key_metric": data.get("key_metric"),
                "key_points": key_points,
                **{
                    key: data.get(key) or fallback
                    for key, fallback in fallbacks.items()
                },
            }
        except Exception as e:
            logger.warning(
                "LLM summarization failed for '%s' (%s: %s); falling back to rule-based summarization",
                title, type(e).__name__, e,
            )
            return self._summarize_with_rules(title, text, entities)

    def _summarize_with_rules(self, title: str, text: str, entities: Dict) -> Dict:
        return {
            "summary": self._extract_lead_sentences(text),
            "headline": title[:100],
            "key_metric": self._extract_key_metric(text),
            "key_points": self._derive_key_points(text, entities),
            **self._derive_components(text, entities),
        }

    @staticmethod
    def _extract_lead_sentences(text: str, n: int = 3) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        meaningful = [
            s.strip() for s in sentences
            if len(s.strip()) > 40 and not s.strip().lower().startswith(("click", "read more", "subscribe", "follow us"))
        ]
        return " ".join(meaningful[:n]) if meaningful else text[:600]

    @staticmethod
    def _derive_key_points(text: str, entities: Dict) -> list:
        """Heuristic analytical bullets for the rule-based (no-LLM) fallback."""
        points: list = []
        geography = entities.get("geography")
        regulatory_body = entities.get("regulatory_body")
        if regulatory_body and geography:
            points.append(f"Regulatory action by {regulatory_body} in {geography}.")
        elif regulatory_body:
            points.append(f"Regulatory action involving {regulatory_body}.")
        trial_phase = entities.get("trial_phase")
        if trial_phase:
            points.append(f"Clinical stage: {trial_phase}.")
        deal_value = entities.get("deal_value")
        if deal_value:
            points.append(f"Reported deal value: {deal_value}.")
        # Pull out sentences that carry hard numbers (results / market size signals).
        for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
            s = sentence.strip()
            if len(points) >= 4:
                break
            if len(s) > 40 and re.search(r"\d", s) and re.search(
                r"(billion|million|%|patient|sales|endpoint|phase|approv|launch)", s, re.IGNORECASE
            ):
                points.append(s)
        return points[:4]

    @staticmethod
    def _extract_key_metric(text: str) -> Optional[str]:
        patterns = [
            r"\$[\d,.]+\s*(?:billion|million|bn|mn)",
            r"p\s*[<=>]\s*0\.\d+",
            r"[\d]+%\s*(?:reduction|improvement|decrease|increase)",
            r"[\d.]+x\s*(?:higher|lower|greater)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(0)
        return None

    @classmethod
    def _derive_components(cls, text: str, entities: Dict) -> Dict[str, Optional[str]]:
        """Extract grounded components for the no-LLM fallback and API consumers."""
        sentences = [
            s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip())
            if len(s.strip()) > 25
        ]
        event_update = sentences[0] if sentences else (text[:400].strip() or None)

        evidence = next((
            s for s in sentences
            if re.search(r"\d", s) and re.search(
                r"(?:endpoint|phase|patient|reduction|response|pfs|survival|sales|deal|\$|₹|%)",
                s, re.IGNORECASE,
            )
        ), None)
        strategic = next((
            s for s in sentences
            if re.search(
                r"(?:first|only|unmet need|standard of care|competitive|addresses|expands access|risk reduction)",
                s, re.IGNORECASE,
            )
        ), None)
        commercial = next((
            s for s in sentences
            if re.search(
                r"(?:launch|commercial|market|sales|revenue|pricing|price|patent|exclusivity|deal value|acquisition)",
                s, re.IGNORECASE,
            )
        ), None)

        status = entities.get("regulatory_status")
        regulator = entities.get("regulatory_body")
        geography = entities.get("geography")
        regulatory_status = None
        if status and status != "not_applicable":
            label = str(status).replace("_", " ").capitalize()
            context = " in ".join(str(v) for v in (regulator, geography) if v)
            regulatory_status = f"{label}{f' - {context}' if context else ''}."

        trial_phase = entities.get("trial_phase")
        clinical_stage = f"Clinical stage: {trial_phase}." if trial_phase else None
        return {
            "event_update": event_update,
            "evidence": evidence,
            "regulatory_status": regulatory_status,
            "clinical_stage": clinical_stage,
            "strategic_significance": strategic,
            "commercial_implications": commercial,
        }
