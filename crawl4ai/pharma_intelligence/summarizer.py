"""
Layer 5: Leadership-Ready Summarization
"""
from __future__ import annotations
import re
from typing import Any, Callable, Dict, Optional

from .prompts import SYSTEM_PHARMA_EXPERT, SUMMARIZATION_PROMPT
from .extraction import _parse_json


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
            return {
                "summary": data.get("summary") or self._extract_lead_sentences(text),
                "headline": data.get("headline", title[:80]),
                "key_metric": data.get("key_metric"),
                "key_points": key_points,
            }
        except Exception:
            return self._summarize_with_rules(title, text, entities)

    def _summarize_with_rules(self, title: str, text: str, entities: Dict) -> Dict:
        return {
            "summary": self._extract_lead_sentences(text),
            "headline": title[:100],
            "key_metric": self._extract_key_metric(text),
            "key_points": self._derive_key_points(text, entities),
        }

    @staticmethod
    def _extract_lead_sentences(text: str, n: int = 4) -> str:
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
