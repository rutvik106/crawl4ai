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
            return {
                "summary": data.get("summary", self._extract_lead_sentences(text)),
                "headline": data.get("headline", title[:80]),
                "key_metric": data.get("key_metric"),
            }
        except Exception:
            return self._summarize_with_rules(title, text, entities)

    def _summarize_with_rules(self, title: str, text: str, entities: Dict) -> Dict:
        return {
            "summary": self._extract_lead_sentences(text),
            "headline": title[:100],
            "key_metric": self._extract_key_metric(text),
        }

    @staticmethod
    def _extract_lead_sentences(text: str, n: int = 2) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        meaningful = [
            s.strip() for s in sentences
            if len(s.strip()) > 40 and not s.strip().lower().startswith(("click", "read more", "subscribe", "follow us"))
        ]
        return " ".join(meaningful[:n]) if meaningful else text[:300]

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
