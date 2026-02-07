from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMConfig:
    """Configuration for LLM provider access."""
    provider: str = "openai/gpt-4o"
    api_token: Optional[str] = None
    base_url: Optional[str] = None
    extra_headers: Optional[dict] = None
