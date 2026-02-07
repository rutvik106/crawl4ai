from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict


@dataclass
class BrowserConfig:
    """Configuration for the browser instance used by AsyncWebCrawler."""
    headless: bool = True
    browser_type: str = "chromium"
    java_script_enabled: bool = True
    user_agent: Optional[str] = None
    proxy: Optional[str] = None
    proxy_config: Optional[Dict[str, str]] = None
    viewport_width: int = 1920
    viewport_height: int = 1080
    ignore_https_errors: bool = True
    extra_args: List[str] = field(default_factory=list)
    text_mode: bool = False
    verbose: bool = False

    # Stealth
    stealth_mode: bool = False
    simulate_human: bool = False

    # Auth & cookies
    cookies: Optional[List[Dict[str, Any]]] = None
    local_storage: Optional[Dict[str, str]] = None
    headers: Optional[Dict[str, str]] = None
    login: Optional[Any] = None  # LoginConfig instance

    # Request interception
    block_images: bool = False
    block_media: bool = False
    blocked_url_patterns: Optional[List[str]] = None
