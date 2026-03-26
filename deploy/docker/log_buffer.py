"""In-memory rotating log buffer.

Attaches a handler to the root logger that keeps the last `maxlen` records
in a deque. Exposes `get_recent_logs()` for the /admin/logs endpoint.
"""
from __future__ import annotations

import logging
import collections
import threading
from datetime import datetime, timezone
from typing import List, Dict, Optional

# Thread-safe deque storing the last N log records as plain dicts.
_buffer: collections.deque = collections.deque(maxlen=2000)
_lock = threading.Lock()

LEVEL_PRIORITY: Dict[str, int] = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


class _BufferingHandler(logging.Handler):
    """Logging handler that pushes records into the in-memory deque."""

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
                "message": self.format(record),
            }
            if record.exc_info:
                entry["exception"] = self.formatException(record.exc_info)
            with _lock:
                _buffer.append(entry)
        except Exception:  # never crash the app
            self.handleError(record)


def attach_to_root_logger(level: int = logging.DEBUG) -> None:
    """Call once at startup to start capturing logs."""
    handler = _BufferingHandler(level=level)
    handler.setFormatter(handler._fmt)
    logging.getLogger().addHandler(handler)


def get_recent_logs(
    limit: int = 200,
    min_level: str = "INFO",
    logger_filter: Optional[str] = None,
) -> List[Dict]:
    """Return the most recent `limit` log entries at >= min_level."""
    threshold = LEVEL_PRIORITY.get(min_level.upper(), 20)
    with _lock:
        snapshot = list(_buffer)

    filtered = [
        entry
        for entry in snapshot
        if LEVEL_PRIORITY.get(entry["level"], 0) >= threshold
        and (logger_filter is None or logger_filter in entry["logger"])
    ]
    return filtered[-limit:]


def buffer_size() -> int:
    with _lock:
        return len(_buffer)
