"""LLM-based structured data extraction."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import ExtractionStrategy


class LLMExtractionStrategy(ExtractionStrategy):
    """Extracts structured data from HTML/text using a language model.

    Args:
        llm_config: An ``LLMConfig`` with provider and token info.
        schema: A JSON schema dict describing the desired output structure.
        extraction_type: "schema" for structured output, "block" for free-form.
        instruction: Natural-language instruction for the LLM.
        extra_args: Additional kwargs forwarded to the LLM call
                    (temperature, top_p, max_tokens, extra_headers, etc.).
    """

    def __init__(
        self,
        llm_config: Any = None,
        schema: Optional[Dict[str, Any]] = None,
        extraction_type: str = "schema",
        instruction: str = "",
        extra_args: Optional[Dict[str, Any]] = None,
        content_length_limit: int = 20000,
    ) -> None:
        self.llm_config = llm_config
        self.schema = schema
        self.extraction_type = extraction_type
        self.instruction = instruction
        self.extra_args = extra_args or {}
        self.content_length_limit = content_length_limit

    def extract(self, url: str, html: str, *args: Any, **kwargs: Any) -> str:
        """Synchronous extraction – delegates to async internally."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self.aextract(url, html)).result()
        return asyncio.run(self.aextract(url, html))

    async def aextract(self, url: str, html: str, *args: Any, **kwargs: Any) -> str:
        """Use the configured LLM to extract structured data from text."""
        try:
            import litellm
        except ImportError:
            raise ImportError("litellm is required for LLM extraction: pip install litellm")

        if self.llm_config is None:
            raise ValueError("llm_config is required for LLM extraction")

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(html)

        call_kwargs: Dict[str, Any] = {
            "model": self.llm_config.provider,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        if self.llm_config.api_token:
            call_kwargs["api_key"] = self.llm_config.api_token
        if self.llm_config.base_url:
            call_kwargs["base_url"] = self.llm_config.base_url

        # Forward extra args
        extra_headers = self.extra_args.pop("extra_headers", None)
        call_kwargs.update(self.extra_args)
        if extra_headers:
            call_kwargs["extra_headers"] = extra_headers
            self.extra_args["extra_headers"] = extra_headers  # restore

        response = await litellm.acompletion(**call_kwargs)
        content = response.choices[0].message.content.strip()
        return self._clean_json_response(content)

    @staticmethod
    def _clean_json_response(text: str) -> str:
        """Best-effort cleanup of LLM JSON output."""
        import re

        # Strip markdown fences
        if "```" in text:
            text = re.sub(r"```(?:json)?\s*\n?", "", text)
            text = text.strip()

        # Find the outermost JSON array or object
        for start_char, end_char in [("[", "]"), ("{", "}")]:
            start = text.find(start_char)
            if start == -1:
                continue
            end = text.rfind(end_char)
            if end > start:
                text = text[start : end + 1]
                break

        # Try parsing; on failure, attempt common fixes
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        # Fix trailing commas before ] or }
        text = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        # Fix truncated JSON: close open brackets/braces
        opens = text.count("[") - text.count("]")
        text_fixed = text
        if opens > 0:
            # Remove last potentially incomplete object
            last_brace = text_fixed.rfind("}")
            last_comma = text_fixed.rfind(",", 0, last_brace + 1 if last_brace > 0 else len(text_fixed))
            if last_comma > 0 and last_brace > 0:
                text_fixed = text_fixed[: last_comma] + "]" * opens
            else:
                text_fixed += "]" * opens
        braces = text_fixed.count("{") - text_fixed.count("}")
        if braces > 0:
            text_fixed += "}" * braces

        try:
            json.loads(text_fixed)
            return text_fixed
        except json.JSONDecodeError:
            pass

        return text

    # ------------------------------------------------------------------ #
    # Prompt builders
    # ------------------------------------------------------------------ #

    def _build_system_prompt(self) -> str:
        parts = [
            "You are a precise data extraction assistant.",
            "Extract information from the provided web page content.",
        ]
        if self.extraction_type == "schema" and self.schema:
            parts.append(
                "Return the extracted data as a JSON array of objects "
                "matching this schema:\n" + json.dumps(self.schema, indent=2)
            )
        else:
            parts.append("Return the extracted data as valid JSON.")

        parts.append("Return ONLY valid JSON – no commentary, no markdown fences.")
        return "\n".join(parts)

    def _build_user_prompt(self, text: str) -> str:
        if self.content_length_limit and len(text) > self.content_length_limit:
            text = text[: self.content_length_limit] + "\n\n[... content truncated ...]"
        parts: List[str] = []
        if self.instruction:
            parts.append(f"Instructions: {self.instruction}\n")
        parts.append(f"Content to extract from:\n\n{text}")
        return "\n".join(parts)
