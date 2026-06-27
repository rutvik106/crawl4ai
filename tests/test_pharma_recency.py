"""Tests for the rolling 24-hour recency filter.

Client requirement: the brief must capture news *published in the last 24 hours*
from the target newswires (PR Newswire, GlobeNewswire, Business Wire — all of
which timestamp in ET). These tests pin the relative-phrase logic, the absolute
date/datetime parsing (including ET → IST conversion) and the never-drop default.
"""

from datetime import datetime

import pytest

from crawl4ai.pharma_intelligence.recency import is_within_last_24h, IST

# Fixed reference: 2026-06-27 14:00 IST → window opens 2026-06-26 14:00 IST.
NOW = datetime(2026, 6, 27, 14, 0, tzinfo=IST)


@pytest.mark.parametrize(
    "item,expected",
    [
        # ── relative phrases ──
        ({"time_ago": "just now"}, True),
        ({"time_ago": "30 minutes ago"}, True),
        ({"time_ago": "2 hours ago"}, True),
        ({"time_ago": "23 hours ago"}, True),
        ({"time_ago": "24 hours ago"}, True),
        ({"time_ago": "25 hours ago"}, False),
        ({"time_ago": "yesterday"}, True),       # part of yesterday is within 24h
        ({"time_ago": "1 day ago"}, True),
        ({"time_ago": "2 days ago"}, False),
        ({"time_ago": "3 weeks ago"}, False),
        ({"time_ago": "1 month ago"}, False),
        # ── absolute date-only ──
        ({"published_date": "June 27, 2026"}, True),
        ({"published_date": "June 26, 2026"}, True),   # yesterday → inclusive
        ({"published_date": "June 25, 2026"}, False),
        ({"published_date": "2026-06-27"}, True),
        ({"published_date": "2026-06-20"}, False),
        # ── absolute datetime with ET timezone (newswire style) ──
        ({"published_date": "June 27, 2026 09:00 ET"}, True),
        ({"published_date": "June 26, 2026 23:30 ET"}, True),
        ({"published_date": "2026-06-27T09:00:00Z"}, True),
        # ── no usable info → keep (never drop) ──
        ({}, True),
        ({"title": "some headline with no date"}, True),
        ({"time_ago": "", "published_date": ""}, True),
    ],
)
def test_is_within_last_24h(item, expected):
    assert is_within_last_24h(item, NOW) is expected


def test_absolute_date_overrides_stale_relative_phrase():
    # Real-world data showed a stale article carrying a hallucinated fresh
    # 'time_ago'. The authoritative absolute publication date must win so the
    # stale item is correctly excluded from a strict 24h brief.
    item = {"time_ago": "11 hours ago", "published_date": "January 1, 2020"}
    assert is_within_last_24h(item, NOW) is False


def test_relative_used_when_no_absolute_date():
    # When only a relative phrase is available, it is honoured.
    assert is_within_last_24h({"time_ago": "2 hours ago"}, NOW) is True
    assert is_within_last_24h({"time_ago": "5 days ago"}, NOW) is False


def test_old_datetime_is_excluded():
    item = {"published_date": "June 20, 2026 09:00 ET"}
    assert is_within_last_24h(item, NOW) is False


def test_no_warning_on_et_timezone(recwarn):
    is_within_last_24h({"published_date": "June 27, 2026 09:00 ET"}, NOW)
    assert not recwarn.list  # dateutil must not warn about the ET abbreviation


def test_defaults_to_current_time_when_now_omitted():
    # Smoke test: should not raise and should keep an undated item.
    assert is_within_last_24h({"title": "x"}) is True
