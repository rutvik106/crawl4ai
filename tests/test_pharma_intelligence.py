"""Tests for the pharma intelligence pipeline.

Focus areas (driven by client feedback):
  1. Never-drop coverage  - no article is silently discarded; low-value / filtered
                             items are demoted to "Other News" instead.
  2. Summary depth        - summaries are substantive (multi-sentence) and carry
                             analytical key_points.
  3. LLM provider routing - the API can select OpenAI or native Anthropic Claude.
"""

import os

import pytest

from crawl4ai.pharma_intelligence import PharmaArticle, PharmaPipeline
from crawl4ai.pharma_intelligence.formatter import PharmaEmailFormatter
from crawl4ai.pharma_intelligence.summarizer import LeadershipSummarizer


# ── Fixtures ──────────────────────────────────────────────────────────────────

HIGH_VALUE_ARTICLE = PharmaArticle(
    title="FDA approves AstraZeneca rare disease gene therapy",
    text=(
        "The U.S. Food and Drug Administration has approved AstraZeneca's gene therapy "
        "for metachromatic leukodystrophy, a rare fatal neurological disorder. The therapy, "
        "priced at $2.8 million per treatment, showed sustained clinical benefit in 31 patients "
        "at 3-year follow-up. AstraZeneca plans to seek EMA and CDSCO approvals within 6 months."
    ),
    url="https://fda.gov/mld-gene-therapy",
    source="FDA",
    published_at="2025-06-19",
)

# A classic "noise" item that the old pipeline would EXCLUDE entirely.
LOW_VALUE_ARTICLE = PharmaArticle(
    title="Wockhardt initiates Phase I study for novel antibiotic",
    text=(
        "Wockhardt has announced the initiation of a Phase I clinical study for its novel "
        "antibiotic candidate targeting multi-drug resistant bacterial infections. The study "
        "will enroll 60 healthy volunteers across sites in the UK."
    ),
    url="https://wockhardt.com/phase1-antibiotic",
    source="Wockhardt",
    published_at="2025-06-19",
)

CONFERENCE_ARTICLE = PharmaArticle(
    title="Cipla presents poster abstract at oncology conference",
    text=(
        "Cipla presented a conference poster abstract describing preclinical data for an "
        "investigational compound at an international oncology congress."
    ),
    url="https://cipla.com/poster",
    source="Cipla",
    published_at="2025-06-19",
)


# ── 1. Never-drop coverage ──────────────────────────────────────────────────────

def test_no_article_is_dropped():
    """Every input article must appear in the output (coverage is never lost)."""
    articles = [HIGH_VALUE_ARTICLE, LOW_VALUE_ARTICLE, CONFERENCE_ARTICLE]
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process(articles)
    # No de-dup collisions expected for these distinct titles.
    assert len(results) == len(articles)


def test_filtered_item_is_demoted_not_excluded():
    """An item that the old pipeline would EXCLUDE (conference/preclinical noise) is
    now retained but flagged demoted and pushed out of the key highlights."""
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process([HIGH_VALUE_ARTICLE, CONFERENCE_ARTICLE])

    by_title = {r.title: r for r in results}
    conf = by_title[CONFERENCE_ARTICLE.title]  # KeyError here would mean it was dropped

    assert conf.demoted is True
    assert conf.demotion_reason  # non-empty explanation
    assert conf.is_key_highlight is False


def test_low_relevance_item_lands_in_other_news():
    """A low-relevance item that isn't hard-filtered is still kept (as Other News)."""
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process([LOW_VALUE_ARTICLE])

    item = results[0]
    assert item.title == LOW_VALUE_ARTICLE.title  # retained, never dropped
    assert item.is_key_highlight is False


def test_approval_with_incidental_exclusion_word_stays_highlighted():
    """A genuine CDSCO approval that incidentally mentions 'preclinical'/'Phase III'
    in its body must NOT be demoted (regression for the missing-news complaint)."""
    article = PharmaArticle(
        title="Sun Pharma gets CDSCO nod for novel oncology biosimilar",
        text=(
            "Sun Pharmaceutical Industries has received approval from CDSCO for its "
            "trastuzumab biosimilar for HER2-positive breast cancer. The approval is "
            "based on analytical, preclinical, and clinical data including a Phase III "
            "equivalence study."
        ),
        url="https://sunpharma.com/cdsco",
        source="Sun Pharma",
    )
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    item = pipeline.process([article])[0]
    assert item.demoted is False
    assert item.is_key_highlight is True


def test_article_body_reaches_summarizer():
    """Summaries must be built from the article body, not just the title."""
    article = PharmaArticle(
        title="FDA approves gene therapy",
        text=(
            "The FDA approved the gene therapy for a rare disorder. The therapy is priced "
            "at $2.8 million per treatment and showed sustained benefit in 31 patients at "
            "three-year follow-up. The company plans EMA and CDSCO filings within months."
        ),
        url="https://fda.gov/x",
        source="FDA",
    )
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    item = pipeline.process([article])[0]
    assert item.summary  # non-empty
    # Body-specific detail (not present in the title) must appear in the summary.
    assert "patients" in item.summary.lower() or "treatment" in item.summary.lower()
    # The carried-through text must not leak into the serialized output.
    assert "text" not in item.to_dict()


def test_high_value_item_is_retained_and_highlighted():
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process([HIGH_VALUE_ARTICLE])
    item = results[0]
    assert item.demoted is False
    assert item.is_key_highlight is True
    assert item.relevance_score > 0


def test_highlights_sorted_before_other_news():
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process([LOW_VALUE_ARTICLE, HIGH_VALUE_ARTICLE, CONFERENCE_ARTICLE])
    # Key highlights must come first in the ordering.
    flags = [r.is_key_highlight for r in results]
    assert flags == sorted(flags, reverse=True)


# ── 2. Summary depth ────────────────────────────────────────────────────────────

def test_rule_based_summary_is_substantive():
    """Rule-based fallback should produce more than a single short line."""
    summarizer = LeadershipSummarizer(llm_client=None)
    out = summarizer.summarize(
        HIGH_VALUE_ARTICLE.title, HIGH_VALUE_ARTICLE.text,
        {"event_type": "approval", "regulatory_body": "FDA", "geography": "United States"},
    )
    # Multiple sentences => meaningfully longer than a one-liner.
    assert out["summary"].count(".") >= 2
    assert "key_points" in out
    assert isinstance(out["key_points"], list)
    assert len(out["key_points"]) >= 1


def test_pipeline_attaches_key_points():
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process([HIGH_VALUE_ARTICLE])
    assert isinstance(results[0].key_points, list)
    assert "key_points" in results[0].to_dict()


def test_llm_summary_parses_key_points():
    """When an LLM returns key_points, they must be surfaced and cleaned."""
    def fake_llm(system, user):
        return (
            '{"summary": "A detailed multi-sentence brief. With numbers.",'
            ' "headline": "FDA approves gene therapy",'
            ' "key_metric": "$2.8M", '
            ' "key_points": ["Approved in the US; EMA/CDSCO filings planned.", "  ", "Market first-in-class."]}'
        )

    summarizer = LeadershipSummarizer(llm_client=fake_llm)
    out = summarizer.summarize("t", "x", {"event_type": "approval"})
    assert out["key_metric"] == "$2.8M"
    # Empty/whitespace bullets are dropped.
    assert out["key_points"] == [
        "Approved in the US; EMA/CDSCO filings planned.",
        "Market first-in-class.",
    ]


# ── 3. Formatter surfaces the new fields ──────────────────────────────────────────

def test_formatter_renders_key_points():
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process([HIGH_VALUE_ARTICLE])
    items = [r.to_dict() for r in results]
    formatter = PharmaEmailFormatter()

    json_summary = formatter.format_json_summary(items)
    all_rendered = json_summary["key_highlights"] + json_summary["other_news"]
    assert "key_points" in all_rendered[0]

    html = formatter.format_report(items)
    assert "<html" in html.lower()


def test_formatter_matches_three_column_specimen():
    """The email table must follow the client's 3-column 'Daily Bites' specimen:
    Molecule/Particular | Highlights (Key) | View Article (no extra columns)."""
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process([HIGH_VALUE_ARTICLE])
    items = [r.to_dict() for r in results]
    html = PharmaEmailFormatter().format_report(items)

    assert "Molecule/Particular" in html
    assert "Highlights (Key)" in html
    assert "View Article" in html
    assert "Read the full article" in html
    # The old 4th "Comments" column header must be gone.
    assert ">Comments<" not in html
    # Exactly three header cells per rendered section table.
    assert html.count("Molecule/Particular") == html.count("Highlights (Key)")


# ── 4. LLM provider routing (OpenAI vs native Anthropic) ──────────────────────────

def test_llm_provider_selection(monkeypatch):
    from api.routers import intelligence

    calls = {"openai": 0, "anthropic": 0}
    monkeypatch.setattr(intelligence, "_make_openai_client", lambda: calls.__setitem__("openai", calls["openai"] + 1) or "openai-client")
    monkeypatch.setattr(intelligence, "_make_anthropic_client", lambda: calls.__setitem__("anthropic", calls["anthropic"] + 1) or "anthropic-client")

    monkeypatch.setenv("PHARMA_LLM_PROVIDER", "anthropic")
    assert intelligence._make_llm_client() == "anthropic-client"

    monkeypatch.setenv("PHARMA_LLM_PROVIDER", "openai")
    assert intelligence._make_llm_client() == "openai-client"

    # Default (unset) falls back to OpenAI.
    monkeypatch.delenv("PHARMA_LLM_PROVIDER", raising=False)
    assert intelligence._make_llm_client() == "openai-client"


def test_clients_return_none_without_keys(monkeypatch):
    from api.routers import intelligence
    from dashboard import db

    # The OpenAI/Groq client also reads keys from DB-stored settings; stub it out
    # so the test is deterministic and never touches the real database.
    monkeypatch.setattr(db, "get_all_settings", lambda: {})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert intelligence._make_openai_client() is None
    assert intelligence._make_anthropic_client() is None
