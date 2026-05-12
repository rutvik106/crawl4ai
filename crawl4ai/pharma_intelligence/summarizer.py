"""
Layer 5: Leadership-Ready Summarization

Generates concise, factual 2-3 sentence summaries optimised for
executive consumption. Rule-based fallback extracts key sentences
when no LLM is available.
"""
from __future__ import annotations
import re
from typing import Any, Callable, Dict, Optional

from .prompts import SYSTEM_PHARMA_EXPERT, SUMMARIZATION_PROMPT
from .extraction import _parse_json


class LeadershipSummarizer:
    """
    Produces 2-3 sentence leadership-ready summaries.

    The summary prioritises:
    1. The concrete outcome (approval/trial result/deal)
    2. The molecule and company involved
    3. The strategic significance (why it matters)
    """

    def __init__(self, llm_client: Optional[Callable[[str, str], str]] = None):
        self.llm_client = llm_client

    def summarize(
        self,
        title: str,
        text: str,
        entities: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Returns dict with: summary (str), headline (str), key_metric (str|None).
        """
        if self.llm_client:
            return self._summarize_with_llm(title, text, entities)
        return self._summarize_with_rules(title, text, entities)

    def _summarize_with_llm(self, title: str, text: str, entities: Dict) -> Dict:
        truncated = text[:3500] if len(text) > 3500 else text
        user_prompt = SUMMARIZATION_PROMPT.format(
            title=title,
            text=truncated,
            molecule=entities.get("molecule") or "N/A",
            company=entities.get("company") or "N/A",
            indication=entities.get("indication") or "N/A",
            event_type=entities.get("event_type") or "N/A",
            existing_context="No prior context available.",
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
        summary = self._extract_lead_sentences(text)
        key_metric = self._extract_key_metric(text)
        return {
            "summary": summary,
            "headline": title[:100],
            "key_metric": key_metric,
        }

    @staticmethod
    def _extract_lead_sentences(text: str, n: int = 2) -> str:
        """Extracts the first n meaningful sentences from text."""
        # Split on sentence boundaries
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        # Filter out very short or boilerplate sentences
        meaningful = [
            s.strip() for s in sentences
            if len(s.strip()) > 40 and not s.strip().lower().startswith(("click", "read more", "subscribe", "follow us"))
        ]
        return " ".join(meaningful[:n]) if meaningful else text[:300]

    @staticmethod
    def _extract_key_metric(text: str) -> Optional[str]:
        """Looks for trial endpoints, deal values, or other key numbers."""
        patterns = [
            r"\$[\d,.]+\s*(?:billion|million|bn|mn)",
            r"p\s*[<=>]\s*0\.\d+",             # p-value
            r"[\d]+%\s*(?:reduction|improvement|decrease|increase)",
            r"[\d.]+x\s*(?:higher|lower|greater)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(0)
        return None
