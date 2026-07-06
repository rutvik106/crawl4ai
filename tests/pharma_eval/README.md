# Pharma Intelligence Categorization Benchmark

A repeatable benchmark for the "Key Highlights vs Other News" categorization
decision, built from Torrent's 35 labeled examples in
`feedbacks/Fine Tuning AI for Daily Bites - 2.pdf`.

## Files
- `daily_bites_examples.json` — the 35 examples (date, particular, title, text,
  expected Key/Other label). Items with `"ambiguous": true` contradict or only
  loosely match the categorization rubric and are known to need client
  calibration — treat mismatches on those as lower-confidence signal.
- `evaluate.py` — loads the dataset, runs it through `PharmaPipeline`, and
  reports accuracy / Key recall / Other agreement / a confusion matrix, both
  including and excluding the ambiguous cases.

## Usage

Free, deterministic, no network/API cost (rule-based fallback path):
```bash
python -m tests.pharma_eval.evaluate
```

Real LLM run (spends API credits; reads keys from the repo `.env` or your
shell environment):
```bash
python -m tests.pharma_eval.evaluate --provider anthropic
python -m tests.pharma_eval.evaluate --provider openai
```

Write full per-item predictions (including generated summaries) to a file for
manual review:
```bash
python -m tests.pharma_eval.evaluate --provider anthropic --out /tmp/results.json
```

## CI / regression guard
`tests/test_pharma_eval.py` runs the free rule-based path and asserts accuracy
doesn't regress below a tracked floor. It intentionally does NOT call a real
LLM (no cost, no flakiness in CI). Run the `--provider anthropic` command
manually whenever you want a real quality/accuracy measurement, e.g. before
and after a prompt or scoring change.

## Extending the dataset
Add more labeled examples (new dates, real crawled articles, or additional
client feedback) as new objects in `daily_bites_examples.json` following the
existing schema. This is how Point 5 ("validate across more dates and source
websites") should be operationalized over time.
