"""
Layer 2: Multi-label Pharma Article Classification

Classifies each article into one or more categories from the pharma taxonomy.
Supports LLM-based classification with rule-based fallback.
"""
from __future__ import annotations
import re
from typing import Any, Callable, Dict, List, Optional

from .prompts import SYSTEM_PHARMA_EXPERT, CLASSIFICATION_PROMPT
from .ontology import ALL_CATEGORIES, REGULATORY_BODIES
from .extraction import _parse_json


class ArticleClassifier:
    """
    Assigns multi-label categories to a pharma article.

    Each article can belong to multiple categories simultaneously.
    Example: an FDA approval for a GLP-1 drug by an Indian company
    would receive: FDA Approval, GLP-1 / Obesity, Indian Market,
    Competitive Intelligence.
    """

    def __init__(self, llm_client: Optional[Callable[[str, str], str]] = None):
        self.llm_client = llm_client
        self._category_patterns = self._build_category_patterns()

    def classify(self, title: str, text: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns dict with keys: categories (list), primary_category (str), therapy_area (str|None).
        """
        if self.llm_client:
            return self._classify_with_llm(title, text, entities)
        return self._classify_with_rules(title, text, entities)

    def _classify_with_llm(self, title: str, text: str, entities: Dict) -> Dict:
        truncated = text[:2000] if len(text) > 2000 else text
        entities_str = ", ".join(f"{k}: {v}" for k, v in entities.items() if v)
        user_prompt = CLASSIFICATION_PROMPT.format(
            title=title, text=truncated, entities=entities_str
        )
        try:
            response = self.llm_client(SYSTEM_PHARMA_EXPERT, user_prompt)
            data = _parse_json(response)
            # Validate categories against known list
            valid_cats = set(ALL_CATEGORIES)
            cats = [c for c in data.get("categories", []) if c in valid_cats]
            if not cats:
                cats = self._classify_with_rules(title, text, entities)["categories"]
            return {
                "categories": cats,
                "primary_category": data.get("primary_category") or cats[0],
                "therapy_area": data.get("therapy_area"),
            }
        except Exception:
            return self._classify_with_rules(title, text, entities)

    def _classify_with_rules(self, title: str, text: str, entities: Dict) -> Dict:
        combined = f"{title} {text[:1500]}".lower()
        categories: List[str] = []

        for category, pattern in self._category_patterns:
            if pattern.search(combined):
                categories.append(category)

        # Inject entity-derived categories
        if entities.get("regulatory_body"):
            rb = entities["regulatory_body"].upper()
            mapping = {
                "FDA": "FDA Approval", "EMA": "EMA Approval",
                "CDSCO": "CDSCO Approval", "NMPA": "NMPA Approval",
                "MHRA": "MHRA Approval",
            }
            if rb in mapping and mapping[rb] not in categories:
                categories.append(mapping[rb])

        if not categories:
            categories = ["Pipeline Update"]

        primary = categories[0]
        therapy_area = next(
            (c for c in categories if c in {
                "Oncology", "GLP-1 / Obesity", "Cardiovascular", "Neurology",
                "Immunology", "Infectious Disease", "Rare Disease", "Gene Therapy",
                "Diabetes", "Respiratory",
            }), None
        )

        return {
            "categories": list(dict.fromkeys(categories)),  # deduplicate, preserve order
            "primary_category": primary,
            "therapy_area": therapy_area,
        }

    @staticmethod
    def _build_category_patterns() -> List[tuple]:
        return [
            ("FDA Approval",           re.compile(r"\bfda.*approv|approv.*fda\b", re.I)),
            ("EMA Approval",           re.compile(r"\bema.*approv|approv.*ema\b", re.I)),
            ("CDSCO Approval",         re.compile(r"\bcdsco.*approv|approv.*cdsco\b", re.I)),
            ("NMPA Approval",          re.compile(r"\bnmpa.*approv|approv.*nmpa\b", re.I)),
            ("MHRA Approval",          re.compile(r"\bmhra.*approv|approv.*mhra\b", re.I)),
            ("Phase III Success",      re.compile(r"phase\s*(?:iii|3).*(?:success|met|positive|achieve)", re.I)),
            ("Phase III Failure",      re.compile(r"phase\s*(?:iii|3).*(?:fail|miss|negative|did not meet)", re.I)),
            ("Clinical Trial",         re.compile(r"clinical\s*trial", re.I)),
            ("M&A Activity",           re.compile(r"acqui(?:re|sition)|merger|takeover|buyout", re.I)),
            ("Licensing Deal",         re.compile(r"licens(?:e|ing).*deal|partner.*agreement|collaborat.*deal", re.I)),
            ("Manufacturing",          re.compile(r"manufactur|plant.*capacity|production.*facilit", re.I)),
            ("Discontinuation",        re.compile(r"discontinu|withdrawn|terminat.*program", re.I)),
            ("Fast Track Designation", re.compile(r"fast.?track.*designat", re.I)),
            ("Breakthrough Therapy",   re.compile(r"breakthrough.*therapy.*designat", re.I)),
            ("Orphan Drug Designation",re.compile(r"orphan.*drug.*designat|orphan.*designat", re.I)),
            ("First Generic Launch",   re.compile(r"first.*generic.*launch|first.*approv.*generic", re.I)),
            ("Biosimilar",             re.compile(r"biosimilar", re.I)),
            ("ANDA Approval",          re.compile(r"\banda\b.*approv|approv.*\banda\b", re.I)),
            ("Patent Expiry",          re.compile(r"patent.*expir|exclusivity.*end|loss.*exclusivity", re.I)),
            ("Label Expansion",        re.compile(r"label.*expan|new.*indication|additional.*indication", re.I)),
            ("Oncology",               re.compile(r"cancer|oncol|tumor|lymphoma|leukemia|melanoma|carcinoma", re.I)),
            ("GLP-1 / Obesity",        re.compile(r"glp.?1|obesity|weight.?loss|semaglutide|tirzepatide", re.I)),
            ("Cardiovascular",         re.compile(r"cardiovascular|cardiac|heart|atrial|ventricular|stroke", re.I)),
            ("Neurology",              re.compile(r"neurol|alzheimer|parkinson|multiple sclerosis|epilep|migraine", re.I)),
            ("Immunology",             re.compile(r"immunol|autoimmune|rheumat|lupus|psoriasis|crohn", re.I)),
            ("Infectious Disease",     re.compile(r"infect|viral|bacterial|hiv|hepatitis|covid|influenza", re.I)),
            ("Rare Disease",           re.compile(r"rare.*disease|ultra.?rare|orphan.*disease", re.I)),
            ("Gene Therapy",           re.compile(r"gene.*therap|gene.*edit|crispr|viral.*vector", re.I)),
            ("Diabetes",               re.compile(r"\bdiabet|insulin|hyperglycemia|type 2|type 1", re.I)),
            ("Respiratory",            re.compile(r"respiratory|asthma|copd|pulmonary|lung.*disease", re.I)),
            ("Indian Market",          re.compile(r"india[n]?\b|cdsco|sun pharma|cipla|dr.?reddy|lupin|torrent|glenmark|aurobindo", re.I)),
            ("Competitive Intelligence", re.compile(r"competitor|market share|pipeline|strategic|competi", re.I)),
        ]
