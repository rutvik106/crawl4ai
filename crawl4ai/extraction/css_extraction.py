"""CSS-based structured data extraction."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from .base import ExtractionStrategy


class JsonCssExtractionStrategy(ExtractionStrategy):
    """Extracts structured JSON from HTML using CSS selectors.

    The schema dict should contain:
        - name: A label for this extraction.
        - baseSelector: CSS selector for repeating container elements.
        - fields: List of field definitions, each with:
            - name: Field name in the output JSON.
            - selector: CSS selector relative to the base element.
            - type: "text", "attribute", or "html".
            - attribute: (required when type="attribute") which HTML attribute to read.
    """

    def __init__(self, schema: Dict[str, Any]) -> None:
        self.schema = schema

    def extract(self, url: str, html: str, *args: Any, **kwargs: Any) -> str:
        """Return a JSON string of extracted items."""
        items = self._extract_items(html)
        return json.dumps(items, ensure_ascii=False)

    @staticmethod
    def generate_schema(
        html: str,
        llm_config: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Use an LLM to auto-generate a CSS extraction schema from sample HTML.

        Args:
            html: A representative HTML snippet.
            llm_config: An ``LLMConfig`` instance specifying the provider & token.

        Returns:
            A schema dict suitable for passing to ``JsonCssExtractionStrategy``.
        """
        if llm_config is None:
            raise ValueError("llm_config is required for schema generation")

        try:
            import litellm
        except ImportError:
            raise ImportError("litellm is required for schema generation: pip install litellm")

        prompt = (
            "Given the following HTML snippet, generate a JSON CSS extraction schema.\n"
            "The schema must have keys: name (str), baseSelector (CSS selector str), "
            "and fields (list of dicts with name, selector, type, and optionally attribute).\n"
            "Return ONLY valid JSON, no explanation.\n\n"
            f"HTML:\n{html}"
        )

        kwargs: Dict[str, Any] = {
            "model": llm_config.provider,
            "messages": [{"role": "user", "content": prompt}],
        }
        if llm_config.api_token:
            kwargs["api_key"] = llm_config.api_token
        if llm_config.base_url:
            kwargs["base_url"] = llm_config.base_url

        response = litellm.completion(**kwargs)
        text = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        return json.loads(text)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _extract_items(self, html: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        base_selector = self.schema.get("baseSelector", "")
        fields = self.schema.get("fields", [])

        if not base_selector:
            return []

        elements = soup.select(base_selector)
        items: List[Dict[str, Any]] = []

        for el in elements:
            item: Dict[str, Any] = {}
            for f in fields:
                name = f["name"]
                selector = f.get("selector", "")
                ftype = f.get("type", "text")
                attribute = f.get("attribute", "")

                target = el.select_one(selector) if selector else el

                if target is None:
                    item[name] = None
                    continue

                if ftype == "text":
                    item[name] = target.get_text(strip=True)
                elif ftype == "attribute" and attribute:
                    item[name] = target.get(attribute)
                elif ftype == "html":
                    item[name] = str(target)
                else:
                    item[name] = target.get_text(strip=True)

            items.append(item)

        return items
