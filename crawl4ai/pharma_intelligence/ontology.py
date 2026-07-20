"""
Pharma intelligence ontology: relevance-scoring dimension weights, entity
taxonomy, exclusion rules.

This module is the single source of truth for all pharma domain knowledge
used across the intelligence pipeline. Update here to affect all layers.
"""
from __future__ import annotations
import re
from typing import Dict, List, Set


# ── Relevance-scoring dimension weights (max points per dimension) ────────────────
# These are the 5 dimensions RelevanceScorer actually evaluates (see scorer.py and
# prompts.RELEVANCE_PROMPT). They replace the older per-event-type KPI_WEIGHTS
# model (fixed weight per event "type", weight 0 = always excluded), which was
# incompatible with the contextual scoring rework: that model would have hard-
# excluded things like Priority Review regardless of evidence/strategic strength,
# undoing the "never automatically exclude/include by category alone" fix.
DEFAULT_DIMENSION_WEIGHTS: Dict[str, int] = {
    "event_maturity": 30,
    "evidence_strength": 20,
    "strategic_significance": 20,
    "commercial_implications": 15,
    "india_torrent_relevance": 15,
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
    # Trial-phase *entry* / progression without reported data (client scope):
    # "advances to Phase 2b", "moves into Phase III", etc. These are checked
    # AFTER the strong-include signals, so a genuine "Phase III met primary
    # endpoint / success" headline is still retained via STRONG_INCLUDE.
    r"\b(?:advance[sd]?|advancing|progress(?:e[sd]|ing)?|moves?|moving|enter(?:s|ing|ed)?|initiat\w*|begins?)\b.{0,40}\bphase\s*(?:i{1,3}b?|[1-4]b?)\b",
    r"\bwithout (?:disclosing|releasing|revealing|sharing|presenting) (?:the )?data\b",
    # Preliminary regulatory interactions / study-design advice (no material
    # development outcome).
    r"\bmulti[- ]agency advice\b",
    r"\bscientific advice\b",
    r"\bregistrational study design\b",
    r"\b(?:advice|guidance|feedback|agreement|input)\b.{0,40}\bstudy design\b",
    r"\bstudy design\b.{0,40}\b(?:advice|guidance|feedback|agreement|input)\b",
    r"\bpre[- ]?IND meeting\b",
    r"\bend[- ]of[- ]phase\s*(?:ii|2)?\b",
    r"\btype [ABCabc] meeting\b",
    # Upcoming conference *presentation* announcements ("to present ... at ...
    # Congress/Meeting 2026"). The subsequent results/data item is covered later.
    r"\bto present\b.{0,80}\b(?:congress|conference|meeting|symposium|summit|session)\b",
    r"\bto present\b.{0,60}\b(?:19|20)\d\d\b",
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
    r"\b(?:ema|ec|european commission|cdsco|nmpa|mhra|tga|pmda)\b.{0,40}\b(?:approv|nod|clear|grant|authori[sz])",
    r"\b(?:approv|nod|clear|grant|authori[sz])\w*\b.{0,40}\b(?:ema|ec|european commission|cdsco|nmpa|mhra|tga|pmda)\b",
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
    # Positive regulatory recommendations (e.g. CHMP recommends X) are a
    # significant milestone the client explicitly wants surfaced as Key
    # Highlights, so they must reach contextual scoring rather than being
    # demoted as "just a review milestone".
    r"\b(?:chmp|advisory committee)\b.{0,40}\b(?:recommend|positive opinion|adopts? a positive)",
    r"\b(?:recommend|positive opinion)\w*\b.{0,40}\b(?:chmp|advisory committee)\b",
]

COMPILED_INCLUDES = [
    re.compile(p, re.IGNORECASE) for p in STRONG_INCLUDE_PATTERNS
]


# ── Scope-override exclusions (checked BEFORE strong-include) ────────────────────
# These categories are out of the newsletter's scope even when the headline
# contains deal/collaboration/acquisition keywords that would otherwise trigger a
# strong-include signal. The classic example is a manufacturing *site*
# acquisition ("Codis Acquires Catalent Nottingham Site") whose "acquires" verb
# would wrongly force-include it as M&A. Genuine drug approvals / pipeline
# transactions essentially never match these headline shapes, so overriding the
# include signal here is safe.
SCOPE_OVERRIDE_PATTERNS: List[str] = [
    # Manufacturing / capacity / facility developments (incl. site acquisitions).
    r"\bspray[- ]dry(?:ing)?\b",
    r"\bmanufacturing (?:capacity|facility|site|plant|expansion|network|operations?)\b",
    r"\b(?:capacity|facility|site|plant) (?:expansion|acquisition)\b",
    r"\bfill[- ]finish\b",
    r"\b(?:acquir\w*|buys?|purchas\w*)\b.{0,40}\b(?:site|facility|plant|campus|manufacturing)\b",
    r"\b(?:site|facility|plant|campus)\b.{0,40}\b(?:acquir\w*|acquisition)\b",
    r"\bcdmo\b.{0,40}\b(?:site|facility|capacity|plant)\b",
    # AI-based collaborations *not* tied to a drug/pipeline asset.
    r"\b(?:ai|artificial intelligence|machine learning)\b.{0,40}\b(?:collaborat|partnership|partner|deal|alliance)",
    r"\b(?:collaborat|partnership|partner|alliance)\b.{0,40}\b(?:ai|artificial intelligence|machine learning)\b",
    # Management / leadership changes.
    r"\b(?:appoint\w*|names?|promotes?|hires?)\b.{0,40}\b(?:ceo|cfo|coo|cto|cso|cmo|chief|president|chair(?:man|person)?|vice president|head of|director)\b",
    r"\b(?:ceo|cfo|coo|cto|cso|cmo|chief executive|president)\b.{0,25}\b(?:steps down|resign\w*|to retire|departs?|appointed|named)\b",
    r"\bboard of directors\b",
    r"\bboard appointment\b",
    # Market forecast / market-size reports.
    r"\bmarket\b.{0,30}\b(?:forecast|projected|projection|to (?:exceed|reach|surpass|grow|hit)|size|cagr|outlook|valuation)\b",
    r"\bforecast\b.{0,20}\b(?:to (?:exceed|reach|surpass)|through|by (?:19|20)\d\d)\b",
    r"\bmarket (?:report|analysis)\b.{0,30}\b(?:19|20)\d\d\b",
    # Webinar / conference *participation* announcements.
    r"\bwebinar\b",
    r"\bfireside chat\b",
    r"\bto (?:join|participate|feature|appear)\b.{0,40}\b(?:webinar|panel|kol|roundtable|discussion|fireside)\b",
    r"\bkol\b.{0,20}\b(?:webinar|event|call|discussion)\b",
]

# A drug/pipeline asset context that should NEG the AI-collaboration override:
# an AI partnership explicitly tied to a named asset / clinical program is in
# scope, so we do not override the include signal in that case.
_DRUG_ASSET_CONTEXT = re.compile(
    r"\b(?:phase\s*(?:i{1,3}|[1-4])|pipeline|clinical (?:trial|program|stage|asset)|"
    r"drug candidate|molecule|nda|bla|maa|indication|therapy for|treatment for)\b",
    re.IGNORECASE,
)

COMPILED_SCOPE_OVERRIDES = [
    re.compile(p, re.IGNORECASE) for p in SCOPE_OVERRIDE_PATTERNS
]


def is_hard_excluded(text: str) -> bool:
    combined = text[:2000]
    return any(p.search(combined) for p in COMPILED_EXCLUSIONS)


def has_strong_include_signal(text: str) -> bool:
    combined = text[:2000]
    return any(p.search(combined) for p in COMPILED_INCLUDES)


def is_scope_override(text: str) -> bool:
    """Definitively out-of-scope categories that override include signals.

    Returns True for manufacturing/facility developments (incl. site
    acquisitions), AI-only collaborations, leadership changes, market-forecast
    reports and webinar/participation announcements. AI collaborations are NOT
    overridden when the text clearly ties them to a named drug/pipeline asset.
    """
    combined = text[:2000]
    for pattern in COMPILED_SCOPE_OVERRIDES:
        if not pattern.search(combined):
            continue
        # Keep AI collaborations that are explicitly linked to a pipeline asset.
        if "ai" in pattern.pattern or "artificial intelligence" in pattern.pattern:
            if _DRUG_ASSET_CONTEXT.search(combined):
                continue
        return True
    return False


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
