"""In-memory rotating log buffer.

Attach to the root logger once at startup; exposes get_recent_logs()
for the /api/logs endpoint so Claude (or any admin) can pull live
server logs without SSH access.
"""
from __future__ import annotations

import logging
import collections
import threading
from datetime import datetime, timezone
from typing import List, Dict, Optional

_buffer: collections.deque = collections.deque(maxlen=2000)
_lock = threading.Lock()

LEVEL_PRIORITY: Dict[str, int] = {
    "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50,
}


class _BufferingHandler(logging.Handler):
    _fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "level": record.levelname,
                "logger": record.name,
                "message": self._fmt.format(record),
            }
            if record.exc_info:
                entry["exception"] = self._fmt.formatException(record.exc_info)
            with _lock:
                _buffer.append(entry)
        except Exception:
            self.handleError(record)


def attach_to_root_logger(level: int = logging.DEBUG) -> None:
    """Call once at startup to start capturing logs."""
    handler = _BufferingHandler(level=level)
    logging.getLogger().addHandler(handler)


def get_recent_logs(
    limit: int = 200,
    min_level: str = "INFO",
    logger_filter: Optional[str] = None,
) -> List[Dict]:
    threshold = LEVEL_PRIORITY.get(min_level.upper(), 20)
    with _lock:
        snapshot = list(_buffer)
    filtered = [
        e for e in snapshot
        if LEVEL_PRIORITY.get(e["level"], 0) >= threshold
        and (logger_filter is None or logger_filter in e["logger"])
    ]
    return filtered[-limit:]


def buffer_size() -> int:
    with _lock:
        return len(_buffer)
