"""
Pharma Intelligence Pipeline - Main Orchestration

Processes raw crawled articles through 6 AI + rule-based layers:
  1. Entity Extraction
  2. Multi-label Classification
  3. Exclusion Filtering (noise reduction)
  4. Relevance Scoring (KPI-weighted)
  5. Deduplication
  6. Summarization

Final output is structured intelligence items split into
"Key Highlights" and "Other News" for leadership consumption.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .extraction import EntityExtractor
from .classifier import ArticleClassifier
from .filter import ExclusionFilter
from .scorer import RelevanceScorer
from .deduplicator import Deduplicator
from .summarizer import LeadershipSummarizer
from .formatter import PharmaEmailFormatter

logger = logging.getLogger(__name__)


@dataclass
class PharmaArticle:
    """Input article from the crawler layer."""
    title: str
    text: str = ""
    summary: str = ""         # existing AI summary if available
    url: str = ""
    source: str = ""
    published_at: str = ""
    category: str = ""        # existing category tag if any
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PharmaIntelligenceResult:
    """Fully processed intelligence item ready for output."""
    # Source
    title: str
    url: str
    source: str
    sources: List[str] = field(default_factory=list)
    published_at: str = ""
    is_consolidated: bool = False

    # Extracted entities
    entities: Dict[str, Any] = field(default_factory=dict)

    # Classification
    categories: List[str] = field(default_factory=list)
    primary_category: str = ""
    therapy_area: Optional[str] = None

    # Exclusion
    excluded: bool = False
    exclusion_reason: str = ""

    # Scoring
    relevance_score: int = 0
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    score_rationale: str = ""
    is_key_highlight: bool = False

    # Summarization
    summary: str = ""
    headline: str = ""
    key_metric: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "sources": self.sources,
            "published_at": self.published_at,
            "is_consolidated": self.is_consolidated,
            "entities": self.entities,
            "categories": self.categories,
            "primary_category": self.primary_category,
            "therapy_area": self.therapy_area,
            "excluded": self.excluded,
            "exclusion_reason": self.exclusion_reason,
            "relevance_score": self.relevance_score,
            "score_breakdown": self.score_breakdown,
            "score_rationale": self.score_rationale,
            "is_key_highlight": self.is_key_highlight,
            "summary": self.summary,
            "headline": self.headline,
            "key_metric": self.key_metric,
        }


class PharmaPipeline:
    """
    End-to-end pharma intelligence processing pipeline.

    Usage:
        pipeline = PharmaPipeline(llm_client=my_llm_fn)
        results = pipeline.process(articles)
        formatter = PharmaEmailFormatter()
        html = formatter.format_report([r.to_dict() for r in results])

    Args:
        llm_client: Optional callable with signature (system: str, user: str) -> str.
                    When provided, all AI layers activate. When None, the pipeline
                    operates in rule-based-only mode (lower quality, zero API cost).
        min_score_threshold: Articles below this score are excluded even after passing
                             the filter layer. Defaults to 10.
        run_deduplication: Whether to cluster duplicate articles. Defaults to True.
    """

    def __init__(
        self,
        llm_client: Optional[Callable[[str, str], str]] = None,
        min_score_threshold: int = 10,
        run_deduplication: bool = True,
    ):
        self.llm_client = llm_client
        self.min_score = min_score_threshold
        self.run_dedup = run_deduplication

        self.extractor = EntityExtractor(llm_client)
        self.classifier = ArticleClassifier(llm_client)
        self.filter_ = ExclusionFilter(llm_client)
        self.scorer = RelevanceScorer(llm_client)
        self.deduplicator = Deduplicator(llm_client)
        self.summarizer = LeadershipSummarizer(llm_client)
        self.formatter = PharmaEmailFormatter()

    def process(
        self,
        articles: List[PharmaArticle],
    ) -> List[PharmaIntelligenceResult]:
        """
        Runs all pipeline layers on a list of raw articles.
        Returns only non-excluded items, sorted by relevance score descending.
        """
        logger.info("[PharmaPipeline] Processing %d articles", len(articles))

        processed: List[Dict[str, Any]] = []
        excluded_count = 0

        for article in articles:
            item = self._process_single(article)
            if item.excluded:
                excluded_count += 1
                logger.debug("[PharmaPipeline] Excluded '%s': %s", article.title, item.exclusion_reason)
            else:
                processed.append(item.to_dict())

        logger.info(
            "[PharmaPipeline] %d passed filter, %d excluded",
            len(processed), excluded_count
        )

        # Deduplication on passed articles
        if self.run_dedup and processed:
            processed = self.deduplicator.cluster(processed)
            logger.info("[PharmaPipeline] After deduplication: %d items", len(processed))

        # Summarize deduplicated items
        results = []
        for item_dict in processed:
            result = self._summarize_item(item_dict)
            results.append(result)

        # Final sort: Key Highlights first, then by score
        results.sort(key=lambda r: (not r.is_key_highlight, -r.relevance_score))
        return results

    def _process_single(self, article: PharmaArticle) -> PharmaIntelligenceResult:
        result = PharmaIntelligenceResult(
            title=article.title,
            url=article.url,
            source=article.source,
            sources=[article.source] if article.source else [],
            published_at=article.published_at,
        )

        text_for_analysis = article.text or article.summary or article.title

        # Layer 1: Entity extraction
        try:
            result.entities = self.extractor.extract(article.title, text_for_analysis)
        except Exception as e:
            logger.warning("Extraction failed for '%s': %s", article.title, e)
            result.entities = {"event_type": "other"}

        event_type = result.entities.get("event_type", "other")

        # Layer 2: Classification
        try:
            classification = self.classifier.classify(
                article.title, text_for_analysis, result.entities
            )
            result.categories = classification["categories"]
            result.primary_category = classification["primary_category"]
            result.therapy_area = classification["therapy_area"]
        except Exception as e:
            logger.warning("Classification failed for '%s': %s", article.title, e)
            result.categories = ["Pipeline Update"]
            result.primary_category = "Pipeline Update"

        # Layer 3: Exclusion filter
        try:
            exclude, reason = self.filter_.should_exclude(
                article.title, text_for_analysis, event_type
            )
            result.excluded = exclude
            result.exclusion_reason = reason
        except Exception as e:
            logger.warning("Filter failed for '%s': %s", article.title, e)
            result.excluded = False

        if result.excluded:
            return result

        # Layer 4: Relevance scoring
        try:
            score_result = self.scorer.score(
                article.title, result.categories, result.entities, event_type
            )
            result.relevance_score = score_result["total_score"]
            result.score_breakdown = score_result.get("breakdown", {})
            result.score_rationale = score_result.get("score_rationale", "")
            result.is_key_highlight = score_result["is_key_highlight"]
        except Exception as e:
            logger.warning("Scoring failed for '%s': %s", article.title, e)

        # Apply minimum score threshold
        if result.relevance_score < self.min_score:
            result.excluded = True
            result.exclusion_reason = f"Below minimum score threshold ({result.relevance_score} < {self.min_score})"
            return result

        return result

    def _summarize_item(self, item_dict: Dict[str, Any]) -> PharmaIntelligenceResult:
        """Applies summarization to a post-deduplication item dict."""
        result = PharmaIntelligenceResult(**{
            k: item_dict.get(k, v)
            for k, v in PharmaIntelligenceResult.__dataclass_fields__.items()  # type: ignore[attr-defined]
            if k in item_dict
        })
        # Re-set fields that need list defaults
        result.sources = item_dict.get("sources", [])
        result.categories = item_dict.get("categories", [])
        result.score_breakdown = item_dict.get("score_breakdown", {})
        result.entities = item_dict.get("entities", {})

        text = item_dict.get("text", item_dict.get("summary", item_dict.get("title", "")))
        try:
            summ = self.summarizer.summarize(
                item_dict.get("title", ""), text, result.entities
            )
            result.summary = summ["summary"]
            result.headline = summ["headline"]
            result.key_metric = summ["key_metric"]
        except Exception as e:
            logger.warning("Summarization failed: %s", e)
            result.summary = item_dict.get("summary", item_dict.get("title", ""))
            result.headline = item_dict.get("title", "")

        return result
