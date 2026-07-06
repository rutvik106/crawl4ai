"""
Pharma intelligence ontology: KPI weights, entity taxonomy, exclusion rules.

This module is the single source of truth for all pharma domain knowledge
used across the intelligence pipeline. Update here to affect all layers.
"""
from __future__ import annotations
import re
from typing import Dict, List, Set


# ── Event Type KPI Weights (0–10 scale) ────────────────────────────────────────────
KPI_WEIGHTS: Dict[str, int] = {
    "new_molecule_approval":      10,
    "new_indication_approval":    9,
    "patent_expiry":              9,
    "indian_competitor_activity": 8,
    "phase3_success":             8,
    "fast_track_designation":     7,
    "breakthrough_therapy":       7,
    "major_licensing_deal":       7,
    "major_ma":                   7,
    "orphan_drug_designation":    7,
    "first_generic_launch":       6,
    "biosimilar_launch":          6,
    "manufacturing_expansion":    5,
    "anda_approval":              5,
    "label_expansion":            5,
    "phase3_failure":             5,
    "clinical_outcome_other":     4,
    "non_critical_ma":            3,
    "rare_disease_update":        3,
    "conference_participation":   1,
    "preclinical_data":           1,
    "trial_initiation":           0,
    "ind_approval":               0,
    "cta_approval":               0,
    "filing_acceptance":          0,
    "priority_review":            0,
}


# ── Multi-label classification taxonomy ──────────────────────────────────────────
ALL_CATEGORIES: List[str] = [
    # Regulatory
    "FDA Approval",
    "EMA Approval",
    "CDSCO Approval",
    "NMPA Approval",
    "MHRA Approval",
    "Other Regulatory Approval",
    "Priority Review",
    "Regulatory Filing",
    "Positive Regulatory Recommendation",
    "Market Withdrawal",
    # Clinical outcomes
    "Phase III Success",
    "Phase III Failure",
    "Clinical Trial",
    # Business events
    "M&A Activity",
    "Licensing Deal",
    "Manufacturing",
    "Pipeline Update",
    "Discontinuation",
    # Designations
    "Fast Track Designation",
    "Breakthrough Therapy",
    "Orphan Drug Designation",
    # Product events
    "First Generic Launch",
    "Biosimilar",
    "ANDA Approval",
    "Patent Expiry",
    "Label Expansion",
    # Therapy areas
    "Oncology",
    "GLP-1 / Obesity",
    "Cardiovascular",
    "Neurology",
    "Immunology",
    "Infectious Disease",
    "Rare Disease",
    "Gene Therapy",
    "Diabetes",
    "Respiratory",
    # Competitive intelligence
    "Competitive Intelligence",
    "Indian Market",
    # Priority tiers
    "Key Highlight",
    "Other News",
]

KEY_HIGHLIGHT_CATEGORIES: Set[str] = {
    "Gene Therapy",
    "Orphan Drug Designation",
    "Fast Track Designation",
    "Breakthrough Therapy",
    "Phase III Success",
    "M&A Activity",
    "First Generic Launch",
    "FDA Approval",
    "EMA Approval",
    "CDSCO Approval",
    "Indian Market",
    "Label Expansion",
    "Patent Expiry",
    "Licensing Deal",
}

KEY_HIGHLIGHT_THERAPY_AREAS: Set[str] = {
    "Oncology",
    "GLP-1 / Obesity",
    "Gene Therapy",
    "Rare Disease",
}

KEY_HIGHLIGHT_SCORE_THRESHOLD = 60

REGULATORY_BODIES: List[str] = [
    "FDA", "EMA", "MHRA", "CDSCO", "NMPA", "TGA", "PMDA",
    "Health Canada", "ANVISA", "SAHPRA",
]

THERAPY_AREAS: List[str] = [
    "Oncology", "Hematology", "Immunology", "Cardiovascular", "Neurology",
    "Psychiatry", "Rare Disease", "Gene Therapy", "GLP-1", "Obesity",
    "Diabetes", "Metabolic", "Respiratory", "Infectious Disease", "HIV",
    "Hepatology", "Gastroenterology", "Dermatology", "Ophthalmology",
    "Urology", "Endocrinology", "Musculoskeletal", "Pain",
]

HARD_EXCLUSION_PATTERNS: List[str] = [
    r"\bIND\b.*(?:approv|filed|submission)",
    r"(?:approv|filed|submission).*\bIND\b",
    r"\bCTA\b.*(?:approv|filed|submission)",
    r"(?:approv|filed|submission).*\bCTA\b",
    r"\bphase\s+[12]\b.*(?:initiat|enroll|start|begin|open)",
    r"(?:initiat|enroll|start|begin|open).*\bphase\s+[12]\b",
    r"\bphase [12] trial\b",
    r"\bpreclinical\b",
    r"\bin vitro\b",
    r"\banimal (?:study|model|data)",
    r"\bconference (?:present|abstract|poster)",
    r"\b(?:abstract|poster) (?:present|at )",
    r"\bfiling (?:accept|receiv)",
    r"(?:accept|receiv).*\bfiling\b",
    r"\bearly discovery\b",
    r"\bdiscovery stage\b",
    r"\bpatent.*filed\b",
    r"\bfiled.*patent\b",
]

COMPILED_EXCLUSIONS = [
    re.compile(p, re.IGNORECASE) for p in HARD_EXCLUSION_PATTERNS
]

STRONG_INCLUDE_PATTERNS: List[str] = [
    # Any major regulator + an approval-type verb within a short window. This keeps
    # genuine approvals (incl. CDSCO/NMPA/MHRA, "nod", "clearance", "marketing
    # authorization") as Key Highlights even when the body incidentally mentions
    # excluded terms like "preclinical" or "Phase II".
    r"\b(?:us)?fda\b.{0,40}\b(?:approv|nod|clear|grant|authori[sz])",
    r"\b(?:approv|nod|clear|grant|authori[sz])\w*\b.{0,40}\b(?:us)?fda\b",
    r"\b(?:ema|cdsco|nmpa|mhra|tga|pmda)\b.{0,40}\b(?:approv|nod|clear|grant|authori[sz])",
    r"\b(?:approv|nod|clear|grant|authori[sz])\w*\b.{0,40}\b(?:ema|cdsco|nmpa|mhra|tga|pmda)\b",
    r"\bmarketing authori[sz]ation\b",
    r"\bnda.*approv",
    r"\bbla.*approv",
    r"\bmaa.*approv",
    r"\bphase\s+(?:iii|3).*(?:success|met|positive|achiev)",
    r"\bpivotal.*trial.*(?:success|met|positive)",
    r"\bacquisi",
    r"\bmerger\b",
    r"\blicensing.*deal\b",
    r"\borphan drug.*designat",
    r"\bfast track.*designat",
    r"\bbreakthrough.*therapy.*designat",
    r"\bfirst.*generic.*launch",
    r"\bpatent.*expir",
    r"\bmarket.*exclus",
    # Priority Review is not automatically Key, but must reach contextual scoring;
    # otherwise exceptional cases are irreversibly demoted before prioritization.
    r"\bpriority review\b",
]

COMPILED_INCLUDES = [
    re.compile(p, re.IGNORECASE) for p in STRONG_INCLUDE_PATTERNS
]


def is_hard_excluded(text: str) -> bool:
    combined = text[:2000]
    return any(p.search(combined) for p in COMPILED_EXCLUSIONS)


def has_strong_include_signal(text: str) -> bool:
    combined = text[:2000]
    return any(p.search(combined) for p in COMPILED_INCLUDES)


# ── Shared regulatory-milestone detector ───────────────────────────────────────
# Previously duplicated (and drifting) between extraction.py and scorer.py.
# Both now delegate here so a fix only needs to happen once.
def detect_regulatory_status(title: str, text: str, event_type: str = "other", truncate: int = 1800) -> str:
    """Classify the regulatory milestone stated by an article.

    Checks the headline first, then the full title+body text, so an article
    about a Priority Review / designation / trial outcome that incidentally
    mentions an *older* approval elsewhere in its body is not mistaken for a
    brand-new final approval.

    Regression note: the final-approval pattern must match present-tense verb
    forms ("FDA approves...", "...gets FDA approval") in addition to the past
    participle ("approved"), otherwise real approval headlines phrased in the
    present tense fall through to the body text, where a cited Phase III
    result can cause a genuine approval to be mislabeled as a mere
    "trial_outcome" (this under-scored several real Key Highlights, e.g.
    FDA-approved products whose approval was backed by Phase III data).
    """
    headline = title.lower()
    combined = f"{title} {text[:truncate]}".lower()
    for haystack in (headline, combined):
        if "priority review" in haystack:
            return "priority_review"
        if re.search(r"\b(?:filing|nda|bla|maa).{0,35}(?:accept|submission)", haystack):
            return "filing_acceptance"
        if re.search(r"\b(?:chmp|advisory committee).{0,35}(?:recommend|opinion)", haystack):
            return "positive_recommendation"
        if re.search(r"\b(?:label (?:update|expansion)|new indication)", haystack):
            return "label_expansion"
        if re.search(r"\b(?:withdraw|revok|discontinu)", haystack):
            return "withdrawal"
        if re.search(r"\b(?:fast track|breakthrough therapy|orphan drug).{0,25}designat", haystack):
            return "designation"
        if re.search(r"\b(?:phase\s*(?:(?:ii(?:b)?\s*/\s*)?iii|3)|pivotal).{0,100}(?:met|show|success|positive|fail|miss|reduc)", haystack):
            return "trial_outcome"
        if (
            re.search(r"\b(?:approv(?:e[sd]?|al|ing)|final approval|marketing authori[sz]ation|gets? (?:fda|ema|cdsco|nmpa) nod)\b", haystack)
            and not re.search(r"\bnot (?:yet )?approved\b", headline)
        ):
            return "final_approval"
        if re.search(r"\blaunch(?:ed|es)?\b", haystack):
            return "launch"
    if event_type == "patent":
        return "exclusivity"
    return "not_applicable" if event_type in ("other", None, "") else str(event_type)
