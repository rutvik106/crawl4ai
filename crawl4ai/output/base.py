"""Base classes for the output pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import CrawlResult


class OutputBackend:
    """Abstract base for output backends.

    Subclasses must implement ``save()`` for single results
    and optionally ``save_many()`` for batch output.
    """

    def save(self, result: CrawlResult, metadata: Optional[Dict[str, Any]] = None) -> None:
        raise NotImplementedError

    def save_many(self, results: List[CrawlResult], metadata: Optional[Dict[str, Any]] = None) -> None:
        for r in results:
            self.save(r, metadata)

    def finalize(self) -> None:
        """Called after all results have been saved. Override for cleanup / flushing."""
        pass


class OutputManager:
    """Dispatches crawl results to one or more output backends.

    Usage::

        manager = OutputManager([
            JsonFileOutput(path="results.json"),
            SQLiteOutput(db_path="crawls.db"),
        ])
        manager.save(result)
        manager.finalize()
    """

    def __init__(self, backends: Optional[List[OutputBackend]] = None) -> None:
        self.backends: List[OutputBackend] = backends or []

    def add(self, backend: OutputBackend) -> None:
        self.backends.append(backend)

    def save(self, result: CrawlResult, metadata: Optional[Dict[str, Any]] = None) -> None:
        for b in self.backends:
            b.save(result, metadata)

    def save_many(self, results: List[CrawlResult], metadata: Optional[Dict[str, Any]] = None) -> None:
        for b in self.backends:
            b.save_many(results, metadata)

    def finalize(self) -> None:
        errors = []
        for b in self.backends:
            try:
                b.finalize()
            except Exception as e:
                backend_name = type(b).__name__
                print(f"[output] {backend_name}.finalize() failed: {e}", flush=True)
                errors.append((backend_name, e))
        if errors:
            names = ", ".join(n for n, _ in errors)
            print(f"[output] WARNING: {len(errors)} backend(s) failed: {names}", flush=True)
