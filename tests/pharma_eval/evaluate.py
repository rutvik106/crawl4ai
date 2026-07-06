"""Benchmark runner for the pharma intelligence pipeline.

Usage (free, deterministic, no network):
    python -m tests.pharma_eval.evaluate

Usage (real LLM, spends API credits - requires ANTHROPIC_API_KEY or
OPENAI_API_KEY/GROQ_API_KEY to be set, e.g. via the repo .env):
    python -m tests.pharma_eval.evaluate --provider anthropic
    python -m tests.pharma_eval.evaluate --provider openai

This does not touch the database or crawl any live sites; it only replays the
35 examples in daily_bites_examples.json through PharmaPipeline and compares
the categorization decision to Torrent's label.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from crawl4ai.pharma_intelligence.pipeline import PharmaArticle, PharmaPipeline

EXAMPLES_PATH = Path(__file__).parent / "daily_bites_examples.json"


def load_examples() -> List[Dict[str, Any]]:
    with open(EXAMPLES_PATH) as f:
        data = json.load(f)
    return data["examples"]


@dataclass
class EvalResult:
    predictions: List[Dict[str, Any]] = field(default_factory=list)

    def _subset(self, examples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        titles = {e["title"] for e in examples}
        return [p for p in self.predictions if p["title"] in titles]

    def summary(self, examples: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        rows = self._subset(examples) if examples is not None else self.predictions
        n = len(rows)
        correct = sum(1 for r in rows if r["expected"] == r["predicted"])
        kk = sum(1 for r in rows if r["expected"] == "KEY" and r["predicted"] == "KEY")
        ko = sum(1 for r in rows if r["expected"] == "KEY" and r["predicted"] == "OTHER")
        ok_ = sum(1 for r in rows if r["expected"] == "OTHER" and r["predicted"] == "KEY")
        oo = sum(1 for r in rows if r["expected"] == "OTHER" and r["predicted"] == "OTHER")
        return {
            "n": n,
            "accuracy": correct / n if n else 0.0,
            "key_recall": kk / (kk + ko) if (kk + ko) else None,
            "other_agreement": oo / (oo + ok_) if (oo + ok_) else None,
            "confusion": {"key_to_key": kk, "key_to_other": ko, "other_to_key": ok_, "other_to_other": oo},
        }

    def mismatches(self, examples: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        rows = self._subset(examples) if examples is not None else self.predictions
        return [r for r in rows if r["expected"] != r["predicted"]]


def run_evaluation(
    llm_client: Optional[Callable[[str, str], str]] = None,
    examples: Optional[List[Dict[str, Any]]] = None,
) -> EvalResult:
    """Process each example individually (dedup off) to keep a clean 1:1
    mapping between an example and its prediction."""
    examples = examples if examples is not None else load_examples()
    pipeline = PharmaPipeline(llm_client=llm_client, min_score_threshold=10, run_deduplication=False)
    result = EvalResult()
    for ex in examples:
        item = pipeline.process([
            PharmaArticle(title=ex["title"], text=ex["text"], source=ex.get("particular", ""))
        ])[0]
        result.predictions.append({
            "date": ex.get("date"),
            "particular": ex.get("particular"),
            "title": ex["title"],
            "expected": ex["expected_label"],
            "predicted": "KEY" if item.is_key_highlight else "OTHER",
            "score": item.relevance_score,
            "status": (item.entities or {}).get("regulatory_status"),
            "molecule": (item.entities or {}).get("molecule"),
            "summary": item.summary,
            "ambiguous": ex.get("ambiguous", False),
        })
    return result


def _make_llm_client(provider: str) -> Optional[Callable[[str, str], str]]:
    if provider == "rule":
        return None
    if provider == "anthropic":
        import anthropic
        api_key = os.environ["ANTHROPIC_API_KEY"]
        model = os.environ.get("PHARMA_LLM_MODEL", "claude-sonnet-4-5-20250929")
        client = anthropic.Anthropic(api_key=api_key)

        def call(system: str, user: str) -> str:
            resp = client.messages.create(
                model=model, system=system,
                messages=[{"role": "user", "content": user}],
                temperature=0.1, max_tokens=2048,
            )
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")

        return call
    if provider == "openai":
        import litellm
        model = os.environ.get("PHARMA_OPENAI_MODEL", "gpt-4o-mini")
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("GROQ_API_KEY")

        def call(system: str, user: str) -> str:
            resp = litellm.completion(
                model=model, api_key=api_key,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.1, max_tokens=2048,
            )
            return resp.choices[0].message.content or ""

        return call
    raise ValueError(f"Unknown provider: {provider}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["rule", "anthropic", "openai"], default="rule")
    parser.add_argument("--out", help="Optional path to write full per-item results as JSON")
    args = parser.parse_args()

    if args.provider != "rule":
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        except Exception:
            pass

    examples = load_examples()
    llm_client = _make_llm_client(args.provider)
    result = run_evaluation(llm_client=llm_client, examples=examples)

    unambiguous = [e for e in examples if not e.get("ambiguous")]
    print(f"\n=== Pharma intelligence categorization benchmark ({args.provider}) ===")
    for label, subset in (("ALL 35 examples", None), ("Excluding ambiguous/contradictory cases", unambiguous)):
        s = result.summary(subset)
        print(f"\n[{label}]  n={s['n']}")
        print(f"  Accuracy:        {s['accuracy']*100:.0f}%")
        print(f"  Key recall:      {s['key_recall']*100:.0f}%" if s["key_recall"] is not None else "  Key recall: n/a")
        print(f"  Other agreement: {s['other_agreement']*100:.0f}%" if s["other_agreement"] is not None else "  Other agreement: n/a")
        print(f"  Confusion: {s['confusion']}")

    print("\nMismatches:")
    for m in result.mismatches():
        flag = " [ambiguous]" if m["ambiguous"] else ""
        print(f"  {m['date']:10} | {m['particular']:28} | {m['expected']:5} -> {m['predicted']:5} "
              f"| score={m['score']:3} | {m['status']}{flag}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(result.predictions, f, indent=2)
        print(f"\nFull results written to {args.out}")


if __name__ == "__main__":
    main()
