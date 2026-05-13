"""
Pharma Intelligence Pipeline - Main Orchestration
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
    title: str
    text: str = ""
    summary: str = ""
    url: str = ""
    source: str = ""
    published_at: str = ""
    category: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PharmaIntelligenceResult:
    title: str
    url: str
    source: str
    sources: List[str] = field(default_factory=list)
    published_at: str = ""
    is_consolidated: bool = False
    entities: Dict[str, Any] = field(default_factory=dict)
    categories: List[str] = field(default_factory=list)
    primary_category: str = ""
    therapy_area: Optional[str] = None
    excluded: bool = False
    exclusion_reason: str = ""
    relevance_score: int = 0
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    score_rationale: str = ""
    is_key_highlight: bool = False
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

    def process(self, articles: List[PharmaArticle]) -> List[PharmaIntelligenceResult]:
        logger.info("[PharmaPipeline] Processing %d articles", len(articles))
        processed: List[Dict[str, Any]] = []
        excluded_count = 0
        for article in articles:
            item = self._process_single(article)
            if item.excluded:
                excluded_count += 1
            else:
                processed.append(item.to_dict())
        logger.info("[PharmaPipeline] %d passed, %d excluded", len(processed), excluded_count)
        if self.run_dedup and processed:
            processed = self.deduplicator.cluster(processed)
        results = [self._summarize_item(d) for d in processed]
        results.sort(key=lambda r: (not r.is_key_highlight, -r.relevance_score))
        return results

    def _process_single(self, article: PharmaArticle) -> PharmaIntelligenceResult:
        result = PharmaIntelligenceResult(
            title=article.title, url=article.url, source=article.source,
            sources=[article.source] if article.source else [],
            published_at=article.published_at,
        )
        text = article.text or article.summary or article.title
        try:
            result.entities = self.extractor.extract(article.title, text)
        except Exception as e:
            logger.warning("Extraction failed for '%s': %s", article.title, e)
            result.entities = {"event_type": "other"}
        event_type = result.entities.get("event_type", "other")
        try:
            clf = self.classifier.classify(article.title, text, result.entities)
            result.categories = clf["categories"]
            result.primary_category = clf["primary_category"]
            result.therapy_area = clf["therapy_area"]
        except Exception as e:
            logger.warning("Classification failed for '%s': %s", article.title, e)
            result.categories = ["Pipeline Update"]
            result.primary_category = "Pipeline Update"
        try:
            exclude, reason = self.filter_.should_exclude(article.title, text, event_type)
            result.excluded = exclude
            result.exclusion_reason = reason
        except Exception as e:
            logger.warning("Filter failed for '%s': %s", article.title, e)
        if result.excluded:
            return result
        try:
            score_result = self.scorer.score(article.title, result.categories, result.entities, event_type)
            result.relevance_score = score_result["total_score"]
            result.score_breakdown = score_result.get("breakdown", {})
            result.score_rationale = score_result.get("score_rationale", "")
            result.is_key_highlight = score_result["is_key_highlight"]
        except Exception as e:
            logger.warning("Scoring failed for '%s': %s", article.title, e)
        if result.relevance_score < self.min_score:
            result.excluded = True
            result.exclusion_reason = f"Below minimum score threshold ({result.relevance_score} < {self.min_score})"
        return result

    def _summarize_item(self, item_dict: Dict[str, Any]) -> PharmaIntelligenceResult:
        result = PharmaIntelligenceResult(**{
            k: item_dict.get(k, v)
            for k, v in PharmaIntelligenceResult.__dataclass_fields__.items()  # type: ignore[attr-defined]
            if k in item_dict
        })
        result.sources = item_dict.get("sources", [])
        result.categories = item_dict.get("categories", [])
        result.score_breakdown = item_dict.get("score_breakdown", {})
        result.entities = item_dict.get("entities", {})
        text = item_dict.get("text", item_dict.get("summary", item_dict.get("title", "")))
        try:
            summ = self.summarizer.summarize(item_dict.get("title", ""), text, result.entities)
            result.summary = summ["summary"]
            result.headline = summ["headline"]
            result.key_metric = summ["key_metric"]
        except Exception as e:
            logger.warning("Summarization failed: %s", e)
            result.summary = item_dict.get("summary", item_dict.get("title", ""))
            result.headline = item_dict.get("title", "")
        return result
