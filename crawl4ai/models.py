from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class MarkdownResult:
    """Holds raw and filtered markdown output from a crawl."""
    raw_markdown: str = ""
    fit_markdown: str = ""

    def __str__(self) -> str:
        return self.raw_markdown

    def __len__(self) -> int:
        return len(self.raw_markdown)

    def __getitem__(self, key):
        return self.raw_markdown[key]


@dataclass
class CrawlResult:
    """Result of a single crawl operation."""
    url: str = ""
    success: bool = True
    status_code: int = 200
    html: str = ""
    cleaned_html: str = ""
    markdown: MarkdownResult = field(default_factory=MarkdownResult)
    extracted_content: Optional[str] = None
    media: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    links: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    session_id: Optional[str] = None
    crawled_urls: List[str] = field(default_factory=list)
