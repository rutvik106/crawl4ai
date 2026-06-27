"""
Rolling 24-hour recency detection.

The client requirement is to capture news *published in the last 24 hours*.
This module centralises that decision so both the crawl-time extraction filter
(``dashboard/engine.py``) and the intelligence pipeline article fetch
(``api/routers/intelligence.py``) apply identical, well-tested logic.

An article dict may carry recency information in a relative field
(``time_ago`` e.g. "2 hours ago") and/or an absolute field (``published_date``,
``published_at`` e.g. "June 27, 2026 09:00 ET"). Relative wording is preferred
because the newswire listing pages render it most reliably; absolute dates are
used as a fallback. When no usable signal exists, the item is kept rather than
silently dropped (consistent with the pipeline's never-drop philosophy).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

# IST (Asia/Kolkata, UTC+5:30) — the business timezone for the daily brief.
IST = timezone(timedelta(hours=5, minutes=30))

# The rolling window length the client asked for.
WINDOW_HOURS = 24

# Fields, in priority order, that may carry recency information on an article dict.
_RELATIVE_FIELDS = ("time_ago",)
_DATE_FIELDS = ("published_at", "published_date", "published", "date")


def _now(now: Optional[datetime]) -> datetime:
    if now is not None:
        return now if now.tzinfo else now.replace(tzinfo=IST)
    return datetime.now(IST)


def _check_relative(raw: str) -> Optional[bool]:
    """Interpret a relative time phrase ('2 hours ago', 'yesterday', ...).

    Returns ``True``/``False`` when the phrase is conclusive, else ``None`` so the
    caller can fall back to absolute-date parsing.
    """
    if not raw:
        return None
    if re.search(r"\bjust now\b|\bmoments?\s+ago\b|\btoday\b", raw):
        return True
    if re.search(r"\b\d+\s*sec(ond)?s?\s*ago\b|\b\d+\s*s\s*ago\b", raw):
        return True
    if re.search(r"\b\d+\s*min(ute)?s?\s*ago\b", raw):
        return True
    m = re.search(r"\b(\d+)\s*h(?:ou)?rs?\s*ago\b", raw) or re.search(r"\b(\d+)\s*hours?\s*ago\b", raw)
    if m:
        return int(m.group(1)) <= WINDOW_HOURS
    # "a/1 day ago" or "yesterday": part of that span is within 24h → keep (inclusive).
    if re.search(r"\byesterday\b|\b(?:a|1)\s*days?\s*ago\b", raw):
        return True
    if re.search(r"\b([2-9]\d*)\s*days?\s*ago\b", raw):
        return False
    if re.search(r"\bweeks?\b|\bmonths?\b|\byears?\b", raw):
        return False
    return None


def _tzinfos() -> Dict[str, Any]:
    """Map the timezone abbreviations the target newswires use (all ET-based,
    plus a few common others) so dateutil resolves them correctly instead of
    warning and discarding them."""
    from dateutil import tz
    eastern = tz.gettz("America/New_York")
    central = tz.gettz("America/Chicago")
    pacific = tz.gettz("America/Los_Angeles")
    london = tz.gettz("Europe/London")
    paris = tz.gettz("Europe/Paris")
    return {
        "ET": eastern, "ET.": eastern, "EDT": eastern, "EST": eastern,
        "CT": central, "CDT": central, "CST": central,
        "PT": pacific, "PDT": pacific, "PST": pacific,
        "GMT": tz.UTC, "UTC": tz.UTC, "Z": tz.UTC,
        "BST": london, "CET": paris, "CEST": paris,
    }


def _parse_datetime(raw: str, ref: datetime) -> Tuple[Optional[datetime], bool]:
    """Parse an explicit date/datetime string.

    Returns ``(dt, has_time)`` where ``dt`` is tz-aware (defaulting to IST) or
    ``None`` if unparseable, and ``has_time`` indicates whether the original
    string carried a time-of-day (vs. a bare date).
    """
    raw = raw.strip()
    if not raw:
        return None, False
    try:
        from dateutil import parser as _dateparser
    except Exception:  # pragma: no cover - dateutil is a hard dependency
        return None, False
    base = ref.astimezone(IST)
    tzinfos = _tzinfos()
    try:
        # Parse twice with different default times: if the parsed time-of-day
        # differs, the string itself supplied a time; if it's identical, it didn't.
        low = _dateparser.parse(raw, fuzzy=True, tzinfos=tzinfos,
                                default=base.replace(hour=0, minute=0, second=0, microsecond=0))
        high = _dateparser.parse(raw, fuzzy=True, tzinfos=tzinfos,
                                 default=base.replace(hour=23, minute=59, second=0, microsecond=0))
    except (ValueError, OverflowError, TypeError):
        return None, False
    has_time = (low.hour, low.minute) == (high.hour, high.minute)
    dt = low if low.tzinfo else low.replace(tzinfo=IST)
    return dt, has_time


def is_within_last_24h(item: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Return ``True`` if ``item`` appears to have been published in the last 24h.

    ``now`` defaults to the current IST time; pass an explicit reference when
    generating a report for a specific point in time.
    """
    ref = _now(now)
    cutoff = ref - timedelta(hours=WINDOW_HOURS)

    # 1) Absolute date / datetime fields are the most authoritative signal — the
    #    target newswires (PR Newswire, GlobeNewswire, Business Wire) display an
    #    exact publication datetime. A relative phrase ("11 hours ago") is more
    #    easily hallucinated by the extractor, so a clean absolute date wins.
    for field in _DATE_FIELDS:
        raw = str(item.get(field) or "").strip()
        if not raw:
            continue
        # The date field may itself contain relative wording (e.g. "Today").
        verdict = _check_relative(raw.lower())
        if verdict is not None:
            return verdict
        dt, has_time = _parse_datetime(raw, ref)
        if dt is None:
            continue
        if has_time:
            return dt >= cutoff
        # Date-only: keep when today or yesterday (IST), since part of yesterday
        # falls inside the rolling window and we never want to drop borderline news.
        return dt.date() >= cutoff.astimezone(IST).date()

    # 2) Relative phrase ("2 hours ago") — used when no absolute date is present.
    relative_raw = " ".join(str(item.get(f) or "") for f in _RELATIVE_FIELDS).lower().strip()
    verdict = _check_relative(relative_raw)
    if verdict is not None:
        return verdict

    # 3) No usable recency info → keep (never silently drop).
    return True
