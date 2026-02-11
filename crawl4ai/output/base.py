"""Output backend manager abstractions."""

from __future__ import annotations

from typing import Iterable, List, Protocol

from crawl4ai.models import CrawlResult


class OutputBackend(Protocol):
    """Protocol implemented by all output backends."""

    def save(self, result: CrawlResult) -> None:
        ...

    def finalize(self) -> None:
        ...


class OutputManager:
    """Dispatch crawl results to a list of output backends."""

    def __init__(self, backends: Iterable[OutputBackend] | None = None) -> None:
        self.backends: List[OutputBackend] = list(backends or [])

    def save(self, result: CrawlResult) -> None:
        for backend in self.backends:
            backend.save(result)

    def save_many(self, results: Iterable[CrawlResult]) -> None:
        for result in results:
            self.save(result)

    def finalize(self) -> None:
        for backend in self.backends:
            finalize = getattr(backend, "finalize", None)
            if callable(finalize):
                finalize()
