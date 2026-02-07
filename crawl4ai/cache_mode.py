from enum import Enum


class CacheMode(Enum):
    """Controls caching behavior for crawl runs."""
    ENABLED = "enabled"
    BYPASS = "bypass"
    READ_ONLY = "read_only"
    WRITE_ONLY = "write_only"
