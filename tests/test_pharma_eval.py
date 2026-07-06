"""Regression guard for the Daily Bites categorization benchmark.

Runs the rule-based (no-LLM, no network, no DB) path over Torrent's 35 labeled
examples (tests/pharma_eval/daily_bites_examples.json) so categorization
accuracy can never silently regress further.

NOTE ON CURRENT BASELINE: as of this test's introduction, the rule-based path
scored ~57% accuracy with only ~17% Key recall. After two targeted bug fixes
(regulatory-status detection recognizing "approves/approval" verb forms, and
scoping the routine-generic demotion guard to the headline instead of the
full body), it measures ~63% accuracy / ~28% Key recall / 100% Other
agreement. That is still a known, tracked weakness (most real Key items still
score under the 60-point threshold in the rule-based path), not a target -
the LLM path scores meaningfully better (~69% accuracy / 50% Key recall
measured with Claude sonnet-4-5 on 2026-07-06) but is not covered by this free
test. The floors below are set at/near the current measured rule-based
baseline so this test catches regressions while further recalibration
(scoring weights / threshold) improves the real numbers over time.

For a real (LLM-backed) accuracy measurement, run manually:
    python -m tests.pharma_eval.evaluate --provider anthropic
"""
from tests.pharma_eval.evaluate import load_examples, run_evaluation


def test_benchmark_dataset_is_well_formed():
    examples = load_examples()
    assert len(examples) == 35
    labels = [e["expected_label"] for e in examples]
    assert labels.count("KEY") == 18
    assert labels.count("OTHER") == 17
    assert all(e["title"] and e["text"] for e in examples)


def test_rule_based_categorization_does_not_regress():
    result = run_evaluation(llm_client=None)
    summary = result.summary()

    # Floors, not targets - see module docstring. Ratchet these up as further
    # categorization recalibration lands.
    assert summary["accuracy"] >= 0.60
    assert summary["other_agreement"] >= 0.95
    assert summary["key_recall"] is not None and summary["key_recall"] >= 0.20


def test_rule_based_never_produces_a_false_key_on_this_set():
    """The rule-based path is currently conservative to a fault: it should not
    (yet) be promoting Other items to Key. If this starts failing, it means
    behavior changed in a way that needs re-validating against Key recall too."""
    result = run_evaluation(llm_client=None)
    other_to_key = result.summary()["confusion"]["other_to_key"]
    assert other_to_key == 0
