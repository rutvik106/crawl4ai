"""Tests for the pharma intelligence pipeline.

Focus areas (driven by client feedback):
  1. Scope filtering      - out-of-scope categories (manufacturing/facility,
                             leadership changes, market forecasts, webinar /
                             "will-present" announcements, trial-phase entry,
                             regulatory-planning) are hard-excluded (dropped);
                             in-scope-but-low-value items are demoted (retained).
  2. Summary depth        - summaries are substantive (multi-sentence) and carry
                             analytical key_points.
  3. LLM provider routing - the API can select OpenAI or native Anthropic Claude.
  4. LLM failure visibility - an LLM error must be logged, never silently
                             swallowed (a bad model name previously degraded
                             the whole brief to rule-based output with zero
                             trace in the logs).
"""

import asyncio
import json
import logging
import os
import sys
import types

import pytest

from crawl4ai.pharma_intelligence import PharmaArticle, PharmaPipeline
from crawl4ai.pharma_intelligence.formatter import PharmaEmailFormatter
from crawl4ai.pharma_intelligence.classifier import ArticleClassifier
from crawl4ai.pharma_intelligence.deduplicator import Deduplicator
from crawl4ai.pharma_intelligence.extraction import EntityExtractor
from crawl4ai.pharma_intelligence.filter import ExclusionFilter
from crawl4ai.pharma_intelligence.scorer import RelevanceScorer
from crawl4ai.pharma_intelligence.summarizer import LeadershipSummarizer


def _failing_llm(system: str, user: str) -> str:
    raise RuntimeError("simulated LLM failure")


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

# A trial-phase-entry item that is now hard-excluded (Phase I initiation).
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

# An in-scope but genuinely low-relevance item: retained (demoted), not dropped.
LOW_VALUE_IN_SCOPE_ARTICLE = PharmaArticle(
    title="Generic ibuprofen tablets reach select regional pharmacies",
    text=(
        "A regional distributor noted that generic ibuprofen tablets are now stocked in "
        "some local pharmacies, with no change to pricing or supply arrangements."
    ),
    url="https://example.com/generic-ibuprofen",
    source="Trade Wire",
    published_at="2025-06-19",
)

# An out-of-scope leadership change that must be hard-excluded.
LEADERSHIP_ARTICLE = PharmaArticle(
    title="Mikart Appoints Darrin Schellin as Chief Executive Officer",
    text=(
        "Mikart, a contract development and manufacturing organization, today announced the "
        "appointment of Darrin Schellin as its new Chief Executive Officer."
    ),
    url="https://example.com/mikart-ceo",
    source="PR Newswire",
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


# ── 1. Scope filtering (hard-exclude vs demote) ──────────────────────────────────

def test_out_of_scope_items_are_dropped():
    """Out-of-scope items (Phase I entry, conference posters, leadership changes)
    are hard-excluded; only the in-scope article survives."""
    articles = [HIGH_VALUE_ARTICLE, LOW_VALUE_ARTICLE, CONFERENCE_ARTICLE, LEADERSHIP_ARTICLE]
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process(articles)
    titles = {r.title for r in results}
    assert HIGH_VALUE_ARTICLE.title in titles
    assert LOW_VALUE_ARTICLE.title not in titles
    assert CONFERENCE_ARTICLE.title not in titles
    assert LEADERSHIP_ARTICLE.title not in titles
    assert pipeline.last_run_stats["excluded_count"] == 3


def test_conference_item_is_excluded():
    """A conference poster / preclinical item is dropped, not demoted."""
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process([HIGH_VALUE_ARTICLE, CONFERENCE_ARTICLE])
    titles = {r.title for r in results}
    assert HIGH_VALUE_ARTICLE.title in titles
    assert CONFERENCE_ARTICLE.title not in titles


def test_leadership_change_is_excluded():
    """Management/leadership appointments are out of scope and dropped."""
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process([LEADERSHIP_ARTICLE])
    assert results == []


def test_low_relevance_in_scope_item_is_retained_and_demoted():
    """A low-relevance but in-scope item is kept (ranked lower), not excluded."""
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process([LOW_VALUE_IN_SCOPE_ARTICLE])

    assert len(results) == 1
    item = results[0]
    assert item.title == LOW_VALUE_IN_SCOPE_ARTICLE.title  # retained, not dropped
    assert item.excluded is False
    assert item.is_key_highlight is False


@pytest.mark.parametrize("title", [
    "Codis Acquires Catalent Nottingham Site for European Spray Drying Capacity",
    "Teva Advances Anti-IL-15 Antibody TEV-408 to Phase 2b in Vitiligo",
    "Moleculin CEO Discusses MIRACLE Trial Results Without Disclosing Data",
    "AMO Pharma Receives Multi-Agency Advice on AMO-02 Registrational Study Design",
    "Altesa to Present Novel Vapendavir Data at ERS Congress 2026",
    "Mikart Appoints Darrin Schellin as Chief Executive Officer",
    "Global Neurotechnology Market Forecast to Exceed USD 50 Billion by 2034",
    "NeuroSense to Join Roth KOL Webinar on ALS Treatment Future",
])
def test_client_out_of_scope_examples_are_excluded(title):
    excluded, _ = ExclusionFilter(None).should_exclude(title, "")
    assert excluded is True


@pytest.mark.parametrize("title", [
    "CHMP Recommends Teclistamab Plus Daratumumab for Relapsed Multiple Myeloma",
    "EC Approves TEPKINLY Combination for Relapsed/Refractory Follicular Lymphoma",
    "Pfizer and Innovent sign global licensing deal worth up to $10.5 billion",
])
def test_client_in_scope_examples_are_included(title):
    excluded, _ = ExclusionFilter(None).should_exclude(title, "")
    assert excluded is False


def test_manufacturing_site_acquisition_overrides_include_signal():
    """A manufacturing *site* acquisition must be excluded even though 'acquires'
    would otherwise trigger the M&A strong-include signal."""
    excluded, reason = ExclusionFilter(None).should_exclude(
        "Codis Acquires Catalent Nottingham Site for Spray Drying Capacity", ""
    )
    assert excluded is True
    assert "scope" in reason.lower()


def test_ai_collaboration_kept_when_linked_to_pipeline_asset():
    """AI collaborations tied to a named drug/pipeline asset stay in scope."""
    from crawl4ai.pharma_intelligence.ontology import is_scope_override
    assert is_scope_override("BigPharma AI collaboration to advance oncology pipeline drug candidate") is False
    assert is_scope_override("BigPharma announces AI collaboration for drug discovery platform") is True


def test_asset_label_formats():
    """Column-1 label: 'molecule (Brand)' for drugs, 'Prefix - A & B' for deals."""
    fmt = PharmaEmailFormatter
    assert fmt._asset_label({}, {"molecule": "epcoritamab", "brand_name": "Tepkinly"}) == "epcoritamab (Tepkinly)"
    assert fmt._asset_label(
        {"counterparties": ["Zydus", "Assertio"]}, {"event_type": "ma"}
    ) == "M&A - Zydus & Assertio"
    assert fmt._asset_label(
        {"counterparties": ["Pfizer", "Innovent"], "categories": ["Licensing Deal"]},
        {"event_type": "licensing"},
    ) == "Licensing - Pfizer & Innovent"
    assert fmt._asset_label(
        {"counterparties": ["Roche", "Repare"]},
        {"event_type": "licensing", "transaction_type": "Collaboration"},
    ) == "Collaboration - Roche & Repare"


def test_rule_extractor_identifies_transaction_type():
    entities = EntityExtractor().extract(
        "Roche and Repare announce oncology collaboration",
        "The companies will jointly develop a named oncology pipeline asset.",
    )
    assert entities["event_type"] == "licensing"
    assert entities["transaction_type"] == "Collaboration"
    assert entities["counterparties"] == []


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


def test_summary_exposes_grounded_daily_bites_components():
    summarizer = LeadershipSummarizer(llm_client=None)
    out = summarizer.summarize(
        HIGH_VALUE_ARTICLE.title,
        HIGH_VALUE_ARTICLE.text,
        {
            "event_type": "approval",
            "regulatory_status": "final_approval",
            "regulatory_body": "FDA",
            "geography": "United States",
            "trial_phase": "Phase III",
        },
    )
    assert out["event_update"]
    assert "$2.8 million" in (out["evidence"] or "")
    assert "Final approval" in (out["regulatory_status"] or "")
    assert out["clinical_stage"] == "Clinical stage: Phase III."
    assert "commercial_implications" in out


# ── 3. Contextual Key vs Other prioritization ─────────────────────────────────

def test_priority_review_is_not_mislabeled_as_final_fda_approval():
    title = "FDA grants Priority Review to Venglustat for Gaucher disease"
    text = (
        "Sanofi's Venglustat received FDA Priority Review after a Phase III study. "
        "If approved, it would be the first US therapy for neurological symptoms."
    )
    entities = EntityExtractor().extract(title, text)
    classified = ArticleClassifier().classify(title, text, entities)

    assert entities["regulatory_status"] == "priority_review"
    assert "Priority Review" in classified["categories"]
    assert "FDA Approval" not in classified["categories"]


def test_priority_review_defaults_to_other_without_india_relevance():
    title = "FDA grants Priority Review to Venglustat for Gaucher disease"
    text = (
        "Sanofi's Venglustat received FDA Priority Review after the Phase III "
        "LEAP2MONO study showed positive efficacy. If approved, it would be the "
        "first US therapy for neurological symptoms of this rare disease."
    )
    entities = EntityExtractor().extract(title, text)
    categories = ArticleClassifier().classify(title, text, entities)["categories"]
    result = RelevanceScorer().score(title, categories, entities, entities["event_type"], text)
    assert result["is_key_highlight"] is False


def test_exceptional_indian_priority_review_can_be_key():
    title = "Zydus saroglitazar NDA granted FDA Priority Review for PBC"
    text = (
        "Zydus Therapeutics received FDA Priority Review for saroglitazar in primary "
        "biliary cholangitis. The Phase IIb/III EPICS-III trial showed a 56.7% versus "
        "9.8% biochemical response. The therapy also holds Orphan Drug and Fast Track "
        "designations for this rare autoimmune liver disease."
    )
    entities = EntityExtractor().extract(title, text)
    categories = ArticleClassifier().classify(title, text, entities)["categories"]
    result = RelevanceScorer().score(title, categories, entities, entities["event_type"], text)
    assert result["is_key_highlight"] is True
    assert result["score_rationale"]

    pipeline_item = PharmaPipeline(llm_client=None).process([
        PharmaArticle(title=title, text=text, source="Zydus")
    ])[0]
    assert pipeline_item.demoted is False
    assert pipeline_item.is_key_highlight is True


def test_routine_generic_fda_approval_remains_other_news():
    title = "Alembic receives FDA final approval for generic oseltamivir"
    text = (
        "Alembic Pharmaceuticals received US FDA final approval for generic "
        "oseltamivir oral suspension for influenza treatment."
    )
    entities = EntityExtractor().extract(title, text)
    categories = ArticleClassifier().classify(title, text, entities)["categories"]
    result = RelevanceScorer().score(title, categories, entities, entities["event_type"], text)
    assert entities["regulatory_status"] == "final_approval"
    assert result["is_key_highlight"] is False


def test_early_stage_large_licensing_deal_remains_other_news():
    title = "Pfizer and Innovent sign $10.5 billion oncology licensing deal"
    text = (
        "The companies signed a global licensing deal worth up to $10.5 billion "
        "covering 12 early-stage cancer therapies. Innovent will lead early development."
    )
    entities = EntityExtractor().extract(title, text)
    categories = ArticleClassifier().classify(title, text, entities)["categories"]
    result = RelevanceScorer().score(title, categories, entities, entities["event_type"], text)
    assert result["is_key_highlight"] is False


def test_meaningful_india_population_expansion_is_key():
    article = PharmaArticle(
        title="Wegovy semaglutide approved for adolescents in India",
        text=(
            "Novo Nordisk's Wegovy semaglutide was approved in India for adolescents "
            "aged 12 years and older with obesity, expanding the indication beyond adults. "
            "The launch opens a new patient population in India's obesity market."
        ),
    )
    item = PharmaPipeline(llm_client=None).process([article])[0]
    assert item.is_key_highlight is True


def test_material_indian_market_shift_can_be_key_without_regulatory_event():
    article = PharmaArticle(
        title="India GLP-1 market momentum slows amid price war",
        text=(
            "India's GLP-1 market momentum slows because of a price war, weak retention, "
            "and prescription plateauing. Companies cut sales targets by 25-30% and hold "
            "more than ₹100 crore of inventory."
        ),
    )
    item = PharmaPipeline(llm_client=None).process([article])[0]
    assert item.is_key_highlight is True


def test_present_tense_approval_headline_is_final_approval_not_trial_outcome():
    """Regression: headlines phrased as 'X approves Y' (present tense) must be
    recognized as final_approval even when the body cites Phase III evidence.
    Previously only the past participle ('approved') was matched, so real
    approval headlines fell through to the body text where the Phase III
    mention caused a mislabel as a mere 'trial_outcome'."""
    title = "FDA approves AstraZeneca Imfinzi durvalumab with BCG for bladder cancer"
    text = (
        "The FDA approved AstraZeneca's Imfinzi durvalumab with BCG for BCG-naive "
        "high-risk non-muscle-invasive bladder cancer. The Phase III POTOMAC trial "
        "showed a 32% reduction in recurrence, progression, or death versus BCG "
        "alone. This is the first new therapy in over 30 years for this setting."
    )
    entities = EntityExtractor().extract(title, text)
    assert entities["regulatory_status"] == "final_approval"


def test_historical_approval_mention_does_not_override_priority_review():
    """An article mainly about a Priority Review that incidentally mentions an
    older, unrelated approval in its body must still resolve to
    priority_review, not final_approval (the two-pass headline-then-body
    ordering must be preserved by the approval-verb regex broadening)."""
    title = "Dizal sunvozertinib gets China NDA acceptance with Priority Review for NSCLC"
    text = (
        "Dizal received NMPA China NDA acceptance with Priority Review for "
        "first-line treatment of EGFR exon20ins NSCLC based on Phase III "
        "WU-KONG28 showing significant PFS benefit. Already approved in US and "
        "China for previously treated EGFR exon20ins NSCLC."
    )
    entities = EntityExtractor().extract(title, text)
    assert entities["regulatory_status"] == "priority_review"


def test_generic_word_in_market_commentary_does_not_force_demote():
    """Regression: the routine-generic demotion guard used to scan the full
    body text, so a market-analysis article that merely mentions 'generic'
    in passing (not as its own headline event) was wrongly force-demoted
    regardless of its score."""
    article = PharmaArticle(
        title="India GLP-1 market momentum slows due to price war",
        text=(
            "Multiple Indian pharma companies see GLP-1 market momentum slow due "
            "to price war including innovator price cuts, weak patient retention, "
            "and prescription plateauing. Generic semaglutide launched post-patent "
            "expiry; market ~Rs 1,900-2,000 crore now moderating. Companies cutting "
            "sales targets 25-30%, inventory build-up over Rs 100 crore."
        ),
    )
    item = PharmaPipeline(llm_client=None).process([article])[0]
    assert item.is_key_highlight is True


def test_generic_approval_headline_still_demoted():
    """The guardrail must still catch genuine routine-generic-approval
    headlines (unaffected by scoping the check to the headline)."""
    title = "Alembic receives FDA final approval for generic oseltamivir"
    text = (
        "Alembic Pharmaceuticals received US FDA final approval for generic "
        "oral suspension of oseltamivir phosphate for influenza treatment."
    )
    entities = EntityExtractor().extract(title, text)
    categories = ArticleClassifier().classify(title, text, entities)["categories"]
    result = RelevanceScorer().score(title, categories, entities, entities["event_type"], text)
    assert result["is_key_highlight"] is False


def test_phase_iib_iii_analysis_is_a_trial_outcome_not_historical_approval():
    title = "Olezarsen Phase IIb/III analysis shows pancreatitis reduction"
    text = (
        "The Phase IIb/III analysis showed an 85% reduction in acute pancreatitis "
        "and a 66% triglyceride reduction. Olezarsen was previously approved for FCS."
    )
    entities = EntityExtractor().extract(title, text)
    assert entities["event_type"] == "clinical_outcome"
    assert entities["regulatory_status"] == "trial_outcome"


# ── 3. Formatter surfaces the new fields ──────────────────────────────────────────

def test_formatter_renders_key_points():
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process([HIGH_VALUE_ARTICLE])
    items = [r.to_dict() for r in results]
    formatter = PharmaEmailFormatter()

    json_summary = formatter.format_json_summary(items)
    all_rendered = json_summary["key_highlights"] + json_summary["other_news"]
    assert "key_points" in all_rendered[0]
    assert all_rendered[0]["particular"]
    assert "regulatory_status" in all_rendered[0]
    assert "classification_confidence" in all_rendered[0]

    html = formatter.format_report(items)
    assert "<html" in html.lower()


def test_formatter_matches_three_column_specimen():
    """The email must be a SINGLE flat 3-column table per the client's specimen:
    Asset / Molecule | News Summary | Source ("Read the full article")."""
    pipeline = PharmaPipeline(llm_client=None, min_score_threshold=10)
    results = pipeline.process([HIGH_VALUE_ARTICLE])
    items = [r.to_dict() for r in results]
    html = PharmaEmailFormatter().format_report(items)

    assert "Asset / Molecule" in html
    assert "News Summary" in html
    assert ">Source<" in html
    assert "Read the full article" in html
    # No Key Highlights / Other News section split in the flat layout.
    assert "Key Highlights" not in html
    assert "Other News" not in html
    # Old badges/columns must be gone.
    assert "DAILY BRIEF" not in html
    assert "Molecule/Particular" not in html
    # Exactly one table header (single flat table).
    assert html.count("Asset / Molecule") == 1


def test_formatter_preserves_asset_label_after_json_round_trip():
    """Stored API items are flattened, so later HTML generation must not lose
    molecule/brand and transaction labels."""
    formatter = PharmaEmailFormatter()
    raw_items = [
        {
            "title": "FDA approves ExampleDrug",
            "summary": "The FDA approved the therapy for the stated indication.",
            "url": "https://example.com/drug",
            "entities": {
                "molecule": "examplemab",
                "brand_name": "ExampleDrug",
                "company": "Example Pharma",
            },
            "therapy_area": "Oncology",
            "is_key_highlight": True,
        },
        {
            "title": "Company A acquires Company B",
            "summary": "Company A agreed to acquire Company B for its pipeline.",
            "url": "https://example.com/deal?x=1&y=2",
            "entities": {"event_type": "ma", "transaction_type": "Acquisition"},
            "counterparties": ["Company A", "Company B"],
            "categories": ["M&A Activity"],
            "is_key_highlight": False,
        },
    ]

    stored = formatter.format_json_summary(raw_items)
    persisted_items = stored["key_highlights"] + stored["other_news"]
    html = formatter.format_report(persisted_items)

    assert "examplemab (ExampleDrug)" in html
    assert "M&amp;A - Company A &amp; Company B" in html
    assert "Example Pharma" not in html
    assert "Oncology" not in html
    assert 'href="https://example.com/deal?x=1&amp;y=2"' in html


def test_formatter_escapes_content_and_rejects_non_web_links():
    html = PharmaEmailFormatter().format_report([
        {
            "title": "Unsafe title",
            "summary": "A <script>alert('x')</script> summary",
            "url": "javascript:alert(1)",
            "asset_label": "Drug <Brand>",
        }
    ])
    assert "<script>" not in html
    assert "Drug &lt;Brand&gt;" in html
    assert "javascript:" not in html
    assert "Read the full article" not in html


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


# ── 5. LLM failure visibility ──────────────────────────────────────────────────
# Regression coverage for a real production incident: PHARMA_LLM_MODEL pointed at
# a model name the Anthropic account could not access. Every layer below caught
# that error and silently fell back to rule-based processing, so the brief
# quietly degraded to one-line summaries and weak categorization with nothing in
# the logs to explain why. These tests assert the failure is now always logged.

def test_anthropic_client_default_model_is_not_the_broken_one(monkeypatch):
    """The old default ('claude-3-5-sonnet-latest') 404s on current Anthropic
    accounts. Guard against silently reintroducing it."""
    from api.routers import intelligence

    captured = {}

    class _FakeMessages:
        def create(self, model, **kwargs):
            captured["model"] = model
            return types.SimpleNamespace(content=[])

    class _FakeAnthropic:
        def __init__(self, api_key):
            self.messages = _FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=_FakeAnthropic))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("PHARMA_LLM_MODEL", raising=False)

    call_llm = intelligence._make_anthropic_client()
    assert call_llm is not None
    call_llm("system", "user")
    assert captured["model"] != "claude-3-5-sonnet-latest"


def test_anthropic_client_respects_explicit_model_override(monkeypatch):
    from api.routers import intelligence

    captured = {}

    class _FakeMessages:
        def create(self, model, **kwargs):
            captured["model"] = model
            return types.SimpleNamespace(content=[])

    class _FakeAnthropic:
        def __init__(self, api_key):
            self.messages = _FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=_FakeAnthropic))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("PHARMA_LLM_MODEL", "claude-opus-4-8")

    call_llm = intelligence._make_anthropic_client()
    call_llm("system", "user")
    assert captured["model"] == "claude-opus-4-8"


@pytest.mark.parametrize(
    "layer_factory, method, args, expected_message_fragment",
    [
        (lambda: EntityExtractor(llm_client=_failing_llm), "extract",
         ("FDA approves drug", "Some article text."), "rule-based extraction"),
        (lambda: ArticleClassifier(llm_client=_failing_llm), "classify",
         ("FDA approves drug", "Some article text.", {}), "rule-based classification"),
        (lambda: RelevanceScorer(llm_client=_failing_llm), "score",
         ("FDA approves drug", [], {}, "approval", "Some article text."), "rule-based scoring"),
        (lambda: LeadershipSummarizer(llm_client=_failing_llm), "summarize",
         ("FDA approves drug", "Some article text.", {}), "rule-based summarization"),
    ],
)
def test_llm_failure_is_logged_not_silent(caplog, layer_factory, method, args, expected_message_fragment):
    layer = layer_factory()
    with caplog.at_level(logging.WARNING):
        result = getattr(layer, method)(*args)
    assert result  # falls back and still returns usable data
    assert any(expected_message_fragment in r.message for r in caplog.records), (
        f"expected a log record mentioning {expected_message_fragment!r}, got: "
        f"{[r.message for r in caplog.records]}"
    )


def test_exclusion_filter_llm_failure_is_logged(caplog):
    filter_ = ExclusionFilter(llm_client=_failing_llm)
    with caplog.at_level(logging.WARNING):
        excluded, reason = filter_.should_exclude(
            "Some ambiguous headline", "Ambiguous article body with no strong signal.", "other"
        )
    assert reason
    assert any("defaulting to include" in r.message for r in caplog.records)


# ── 6. Configurable Key Highlight threshold ────────────────────────────────────
# Regression coverage for /intelligence/config's "Key Highlight threshold" field,
# which used to be saved to the database but silently ignored - the pipeline
# always used the hardcoded KEY_HIGHLIGHT_SCORE_THRESHOLD constant regardless of
# what was configured. It's now threaded through PharmaPipeline -> RelevanceScorer,
# so changing it from the config UI actually changes behavior.

def _fake_llm_fixed_score(total_score: int):
    def call(system, user):
        return (
            f'{{"total_score": {total_score}, "breakdown": {{"event_maturity": 30,'
            f' "evidence_strength": 10, "strategic_significance": 10,'
            f' "commercial_implications": 3, "india_torrent_relevance": 2}},'
            f' "score_rationale": "test", "is_key_highlight": false,'
            f' "classification_confidence": 0.8}}'
        )
    return call


# ── 7. Configurable dimension weights (replaces the old, incompatible KPI_WEIGHTS) ──
# The KPI Weights config UI section used to expose a per-event-type weight model
# (e.g. "Priority Review" pinned to weight 0 = always excluded) that directly
# conflicts with the contextual scoring rework - it would silently override the
# "never auto-include/exclude by category alone" fixes. It has been replaced by
# configurable weights on the 5 real scoring dimensions the rubric evaluates.

def test_default_dimension_weights_sum_to_the_original_100_point_scale():
    from crawl4ai.pharma_intelligence.ontology import DEFAULT_DIMENSION_WEIGHTS
    assert sum(DEFAULT_DIMENSION_WEIGHTS.values()) == 100
    assert DEFAULT_DIMENSION_WEIGHTS == {
        "event_maturity": 30,
        "evidence_strength": 20,
        "strategic_significance": 20,
        "commercial_implications": 15,
        "india_torrent_relevance": 15,
    }


def test_rule_based_breakdown_scales_to_custom_dimension_weights():
    """Boosting india_torrent_relevance's max from 15 to 30 should roughly
    double that dimension's contribution for an India-relevant article, while
    leaving other dimensions (and the rubric's relative behavior) unchanged."""
    title = "Torrent Pharma launches new drug in India"
    text = "Torrent Pharma launches a new drug in the Indian market."
    entities = EntityExtractor().extract(title, text)
    categories = ArticleClassifier().classify(title, text, entities)["categories"]

    default_result = RelevanceScorer().score(title, categories, entities, entities["event_type"], text)
    boosted_result = RelevanceScorer(dimension_weights={"india_torrent_relevance": 30}).score(
        title, categories, entities, entities["event_type"], text
    )

    assert boosted_result["breakdown"]["india_torrent_relevance"] == (
        default_result["breakdown"]["india_torrent_relevance"] * 2
    )
    # Other dimensions are untouched by an india-only override.
    for dim in ("event_maturity", "evidence_strength", "strategic_significance", "commercial_implications"):
        assert boosted_result["breakdown"][dim] == default_result["breakdown"][dim]
    assert boosted_result["total_score"] > default_result["total_score"]


def test_boosting_india_relevance_can_recover_a_torrent_relevant_miss():
    """Concrete regression: Selpercatinib's India launch (from the Daily Bites
    benchmark set) scores just under the Key threshold at default weights but
    clears it once India/Torrent relevance is weighted more heavily - proving
    the new config knob has real effect, unlike the KPI Weights section it
    replaces."""
    article = PharmaArticle(
        title="Eli Lilly launches selpercatinib in India after CDSCO approval",
        text=(
            "Eli Lilly launched selpercatinib in India post CDSCO approval for "
            "RET-altered locally advanced/metastatic solid tumours including NSCLC "
            "and thyroid cancers. Oral targeted therapy demonstrating rapid durable "
            "responses including CNS activity. Globally approved selective RET "
            "inhibitor; now introduced in India."
        ),
    )
    default_item = PharmaPipeline(llm_client=None).process([article])[0]
    assert default_item.is_key_highlight is False
    assert default_item.relevance_score == 49

    boosted_item = PharmaPipeline(
        llm_client=None, dimension_weights={"india_torrent_relevance": 30}
    ).process([article])[0]
    assert boosted_item.is_key_highlight is True


def test_config_endpoint_exposes_dimension_weights_and_drops_legacy_keys(monkeypatch):
    """/intelligence/config must serve the new dimension_weights default and
    must never resurface the old kpi_weights / bundle_configs keys, even if an
    older stored row still has them (pre-migration DB state)."""
    from api.routers import intelligence

    monkeypatch.setattr(intelligence, "_ensure_tables", lambda: None)

    class _FakeCursor:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def execute(self, *a, **k):
            pass
        def fetchone(self):
            return {"config": {"kpi_weights": {"priority_review": 0}, "bundle_configs": {"a": 1}}}

    class _FakeConn:
        def cursor(self, **k):
            return _FakeCursor()
        def close(self):
            pass

    monkeypatch.setattr(intelligence, "_connect", lambda: _FakeConn())

    cfg = intelligence._get_config()
    assert "kpi_weights" not in cfg
    assert "bundle_configs" not in cfg
    assert cfg["dimension_weights"] == {
        "event_maturity": 30, "evidence_strength": 20, "strategic_significance": 20,
        "commercial_implications": 15, "india_torrent_relevance": 15,
    }
    assert cfg["schedule_enabled"] is False
    assert cfg["schedule_time"] == "08:30"


def test_report_generation_reads_dimension_weights_from_config(monkeypatch):
    from api.routers import intelligence

    monkeypatch.setattr(
        intelligence, "_get_config",
        lambda: {
            "min_score_threshold": 0,
            "key_highlight_score_threshold": 60,
            "dimension_weights": {"india_torrent_relevance": 30},
        },
    )
    monkeypatch.setattr(intelligence, "_make_llm_client", lambda: None)
    monkeypatch.setattr(intelligence, "_store_result", lambda *a, **k: None)

    captured_kwargs = {}
    original_init = intelligence.PharmaPipeline.__init__

    def capturing_init(self, *args, **kwargs):
        captured_kwargs.update(kwargs)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(intelligence.PharmaPipeline, "__init__", capturing_init)

    articles = [intelligence._to_pharma_article(intelligence.ArticleInput(
            title="Torrent Pharma launches new drug in India",
            text="Torrent Pharma launches a new drug in the Indian market.",
        ).model_dump())]
    intelligence._generate_report("2026-01-01", articles)

    assert captured_kwargs.get("dimension_weights") == {"india_torrent_relevance": 30}


def test_relevance_scorer_respects_custom_threshold():
    title = "FDA approves ExampleDrug for a rare condition"
    text = "The FDA approved ExampleDrug for a rare condition based on clinical data."
    entities = {"regulatory_status": "final_approval", "event_type": "approval"}
    llm = _fake_llm_fixed_score(55)

    default_result = RelevanceScorer(llm_client=llm).score(title, [], entities, "approval", text)
    assert default_result["total_score"] == 55
    assert default_result["is_key_highlight"] is False  # 55 < default threshold of 60

    lowered_result = RelevanceScorer(llm_client=llm, key_highlight_threshold=50).score(
        title, [], entities, "approval", text
    )
    assert lowered_result["is_key_highlight"] is True  # 55 >= 50


def test_pipeline_threads_key_highlight_threshold_to_scorer():
    article = PharmaArticle(
        title="FDA approves ExampleDrug for a rare condition",
        text="The FDA approved ExampleDrug for a rare condition based on clinical data.",
    )
    llm = _fake_llm_fixed_score(55)

    default_item = PharmaPipeline(llm_client=llm, min_score_threshold=0).process([article])[0]
    assert default_item.is_key_highlight is False

    lowered_item = PharmaPipeline(
        llm_client=llm, min_score_threshold=0, key_highlight_threshold=50
    ).process([article])[0]
    assert lowered_item.is_key_highlight is True


def test_report_generation_reads_key_highlight_threshold_from_config(monkeypatch):
    """The report generator must actually read
    key_highlight_score_threshold from the stored config and pass it to
    PharmaPipeline - it used to be fetched into pharma_cfg and then never
    used, so the config UI's "Key Highlight threshold" field was a no-op."""
    from api.routers import intelligence

    monkeypatch.setattr(
        intelligence, "_get_config",
        lambda: {"min_score_threshold": 0, "key_highlight_score_threshold": 50},
    )
    monkeypatch.setattr(intelligence, "_make_llm_client", lambda: _fake_llm_fixed_score(55))
    monkeypatch.setattr(intelligence, "_store_result", lambda *a, **k: None)

    captured_kwargs = {}
    original_init = intelligence.PharmaPipeline.__init__

    def capturing_init(self, *args, **kwargs):
        captured_kwargs.update(kwargs)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(intelligence.PharmaPipeline, "__init__", capturing_init)

    articles = [intelligence._to_pharma_article(intelligence.ArticleInput(
            title="FDA approves ExampleDrug for a rare condition",
            text="The FDA approved ExampleDrug for a rare condition based on clinical data.",
        ).model_dump())]
    summary = intelligence._generate_report("2026-01-01", articles)

    assert captured_kwargs.get("key_highlight_threshold") == 50
    assert summary["key_highlights_count"] == 1  # 55 >= configured threshold of 50


def test_process_endpoint_starts_background_run_and_returns_202(monkeypatch):
    from api.routers import intelligence

    calls = []
    monkeypatch.setattr(
        intelligence,
        "start_report_run",
        lambda date, articles: calls.append((date, articles)) or True,
    )
    payload = intelligence.ProcessRequest(date="2026-01-01")
    response = asyncio.run(
        intelligence.process_articles(payload, current_user={"username": "test"})
    )

    assert response.status_code == 202
    assert calls == [("2026-01-01", None)]
    assert json.loads(response.body)["status"] == "pending"


def test_scheduled_run_generates_uploads_and_emails_pdf_link(monkeypatch):
    from api.routers import intelligence

    statuses = []
    stored = []
    sent = []
    report = {
        "key_highlights_count": 1,
        "other_news_count": 2,
        "key_highlights": [{"title": "A"}],
        "other_news": [{"title": "B"}, {"title": "C"}],
    }
    monkeypatch.setattr(
        intelligence,
        "_set_run_status",
        lambda date, status, **kwargs: statuses.append((date, status, kwargs)),
    )
    monkeypatch.setattr(intelligence, "_generate_report", lambda date, articles: dict(report))
    monkeypatch.setattr(intelligence, "_build_report_pdf", lambda date, items: b"%PDF-test")
    monkeypatch.setattr(
        intelligence,
        "_upload_report_pdf",
        lambda date, data: "https://blob.example/report.pdf",
    )
    monkeypatch.setattr(
        intelligence,
        "_get_config",
        lambda: {
            "schedule_recipients": "client@example.com",
            "schedule_email_subject": "Daily Brief",
        },
    )
    monkeypatch.setattr(
        intelligence,
        "_send_report_link_email",
        lambda *args: sent.append(args),
    )
    monkeypatch.setattr(
        intelligence,
        "_store_result",
        lambda date, result: stored.append((date, result)),
    )

    intelligence._run_report_job("2026-07-22", deliver_email=True)

    assert statuses[0][1] == "running"
    assert statuses[-1] == (
        "2026-07-22",
        "completed",
        {"pdf_url": "https://blob.example/report.pdf", "email_sent": True},
    )
    assert stored[-1][1]["pdf_url"] == "https://blob.example/report.pdf"
    assert sent[0][2] == "https://blob.example/report.pdf"
    assert sent[0][3] == "client@example.com"


def test_scheduler_registers_daily_pharma_job_in_ist(monkeypatch):
    from api.routers import intelligence
    from dashboard import scheduler as scheduler_module

    class _Job:
        next_run_time = "next-run"

    class _Scheduler:
        def __init__(self):
            self.added = None

        def get_job(self, job_id):
            return _Job() if self.added and job_id == "pharma_intelligence_daily" else None

        def remove_job(self, job_id):
            self.added = None

        def add_job(self, func, **kwargs):
            self.added = (func, kwargs)

    fake_scheduler = _Scheduler()
    monkeypatch.setattr(scheduler_module, "_scheduler", fake_scheduler)
    monkeypatch.setattr(
        intelligence,
        "_get_config",
        lambda: {"schedule_enabled": True, "schedule_time": "09:15"},
    )

    scheduler_module._register_pharma_schedule()

    assert fake_scheduler.added is not None
    _, kwargs = fake_scheduler.added
    assert kwargs["id"] == "pharma_intelligence_daily"
    assert "hour='9'" in str(kwargs["trigger"])
    assert "minute='15'" in str(kwargs["trigger"])
    assert str(kwargs["trigger"].timezone) == "Asia/Kolkata"


def test_deduplicator_llm_failure_is_logged(caplog):
    """Titles are deliberately dissimilar (so the cheap Jaccard check can't
    short-circuit) while entities match, forcing the LLM verification path."""
    dedup = Deduplicator(llm_client=_failing_llm)
    a = {"title": "Regulator grants marketing clearance for new therapy",
         "summary": "x", "entities": {"molecule": "moleculex", "event_type": "approval",
                                       "regulatory_body": "FDA", "company": "acme"}}
    b = {"title": "Acme announces milestone decision from health authority",
         "summary": "y", "entities": {"molecule": "moleculex", "event_type": "approval",
                                       "regulatory_body": "FDA", "company": "acme"}}
    with caplog.at_level(logging.WARNING):
        is_dup = dedup._are_duplicates(a, b)
    assert is_dup is False  # fails safe: treated as not-duplicate rather than merged
    assert any("dedup check failed" in r.message for r in caplog.records)
