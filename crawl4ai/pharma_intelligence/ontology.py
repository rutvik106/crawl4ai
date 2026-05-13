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
    r"\bpriority review (?:grant|designat)",
    r"\bearly discovery\b",
    r"\bdiscovery stage\b",
    r"\bpatent.*filed\b",
    r"\bfiled.*patent\b",
]

COMPILED_EXCLUSIONS = [
    re.compile(p, re.IGNORECASE) for p in HARD_EXCLUSION_PATTERNS
]

STRONG_INCLUDE_PATTERNS: List[str] = [
    r"\bfda.*approv",
    r"\bapprov.*fda",
    r"\bema.*approv",
    r"\bapprov.*ema",
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
