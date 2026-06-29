"""Tests for the recall/anti-drop fixes:

  * lenient JSON parsing salvages articles from truncated LLM output
  * provider-aware API key resolution (Claude / Groq / OpenAI)
  * relative-time age heuristic used for adaptive scroll stopping
"""
import os

import pytest

from crawl4ai.deep_crawler import _parse_articles_lenient
from crawl4ai.page_actions import _phrase_age_hours
from dashboard.engine import _resolve_llm_key, DEFAULT_LLM_PROVIDER


# ---------------------------------------------------------------- #
# Lenient JSON salvage
# ---------------------------------------------------------------- #

def test_lenient_parses_well_formed_array():
    raw = '[{"title": "A"}, {"title": "B"}]'
    assert _parse_articles_lenient(raw) == [{"title": "A"}, {"title": "B"}]


def test_lenient_salvages_truncated_array():
    # Array cut off mid-way (model hit max_tokens). The two complete objects
    # must still be recovered instead of dropping the whole batch.
    raw = '[{"title": "A", "summary": "x"}, {"title": "B", "summary": "y"}, {"title": "C'
    out = _parse_articles_lenient(raw)
    assert [o["title"] for o in out] == ["A", "B"]


def test_lenient_ignores_braces_inside_strings():
    raw = '[{"title": "Deal worth {$1B}", "summary": "a}b"}]'
    out = _parse_articles_lenient(raw)
    assert out == [{"title": "Deal worth {$1B}", "summary": "a}b"}]


def test_lenient_handles_single_object():
    assert _parse_articles_lenient('{"title": "Solo"}') == [{"title": "Solo"}]


def test_lenient_empty_returns_empty():
    assert _parse_articles_lenient("") == []
    assert _parse_articles_lenient("not json at all") == []


# ---------------------------------------------------------------- #
# Provider-aware key resolution
# ---------------------------------------------------------------- #

def test_resolve_key_anthropic_from_settings():
    settings = {"anthropic_api_key": "sk-ant-xyz", "groq_api_key": "gsk-bad"}
    assert _resolve_llm_key("anthropic/claude-sonnet-4-5", settings) == "sk-ant-xyz"


def test_resolve_key_groq():
    settings = {"groq_api_key": "gsk-123", "anthropic_api_key": "sk-ant"}
    assert _resolve_llm_key("groq/llama-3.1-8b-instant", settings) == "gsk-123"


def test_resolve_key_openai():
    settings = {"openai_api_key": "sk-oai"}
    assert _resolve_llm_key("openai/gpt-4o", settings) == "sk-oai"


def test_resolve_key_env_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    assert _resolve_llm_key("anthropic/claude-sonnet-4-5", {}) == "sk-ant-env"


def test_default_provider_is_claude():
    assert DEFAULT_LLM_PROVIDER.startswith("anthropic/")


# ---------------------------------------------------------------- #
# Relative-time age heuristic
# ---------------------------------------------------------------- #

@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("just now", 0.0),
        ("today", 0.0),
        ("30 minutes ago", 0.5),
        ("2 hours ago", 2.0),
        ("yesterday", 24.0),
        ("3 days ago", 72.0),
        ("1 week ago", 168.0),
    ],
)
def test_phrase_age_hours(phrase, expected):
    assert _phrase_age_hours(phrase) == pytest.approx(expected)


def test_phrase_age_unknown_returns_none():
    assert _phrase_age_hours("sometime") is None
