"""
Modular prompt templates for each pharma intelligence pipeline layer.

Design principles:
- One prompt per concern (extraction, classification, exclusion, scoring, summarization)
- Each prompt returns structured JSON
- Prompts are independently testable and tunable
- System prompt establishes expert persona shared across all layers
"""

SYSTEM_PHARMA_EXPERT = """You are a senior pharma intelligence analyst with 20+ years of experience 
in regulatory affairs, clinical development, and competitive intelligence. 
You specialize in filtering signal from noise for leadership teams at pharmaceutical companies.
Your output is ALWAYS valid JSON. Never include text, markdown, or explanations outside the JSON object."""


EXTRACTION_PROMPT = """\
Extract structured pharma entities from the article below.

Article Title: {title}
Article Text: {text}

Return a JSON object with EXACTLY these fields (use null if not found/applicable):
{{
  "molecule": "primary drug/molecule INN name (prefer INN over brand)",
  "brand_name": "brand name if mentioned, else null",
  "company": "primary pharma company involved",
  "indication": "disease or medical condition being treated",
  "trial_phase": "Phase I / Phase II / Phase III / Phase IV / null",
  "geography": "country or region where the event occurred",
  "regulatory_body": "FDA / EMA / CDSCO / NMPA / MHRA / other / null",
  "event_type": "one of: approval | clinical_outcome | ma | licensing | discontinuation | label_expansion | designation | generic_launch | manufacturing | patent | conference | preclinical | other",
  "deal_value": "deal value in USD millions if stated, else null"
}}"""


CLASSIFICATION_PROMPT = """\
Classify this pharma article into ALL applicable categories from the list below.
An article commonly has 3-5 categories simultaneously.

Article Title: {title}
Article Text (excerpt): {text}
Extracted Entities: {entities}

Category list:
REGULATORY: FDA Approval | EMA Approval | CDSCO Approval | NMPA Approval | MHRA Approval | Other Regulatory Approval
CLINICAL: Phase III Success | Phase III Failure | Clinical Trial
BUSINESS: M&A Activity | Licensing Deal | Manufacturing | Pipeline Update | Discontinuation
DESIGNATIONS: Fast Track Designation | Breakthrough Therapy | Orphan Drug Designation
PRODUCT: First Generic Launch | Biosimilar | ANDA Approval | Patent Expiry | Label Expansion
THERAPY AREA: Oncology | GLP-1 / Obesity | Cardiovascular | Neurology | Immunology | Infectious Disease | Rare Disease | Gene Therapy | Diabetes | Respiratory
MARKET: Indian Market | Competitive Intelligence

Return JSON:
{{
  "categories": ["Category1", "Category2"],
  "primary_category": "the single most important category",
  "therapy_area": "primary therapy area from the THERAPY AREA list, or null"
}}"""


EXCLUSION_PROMPT = """\
Determine if this pharma article should be EXCLUDED from a leadership intelligence brief.

Article Title: {title}
Article Text (excerpt): {text}
Detected Event Type: {event_type}

EXCLUDE if primarily about:
- IND or CTA filing/approval (not a final regulatory approval)
- Phase I or Phase II trial initiation or enrollment announcements
- Conference presentations, poster abstracts
- Preclinical, in vitro, or animal study data
- Filing acceptance for review (not the decision itself)
- Priority review designation (not the final approval)
- Early discovery or research stage news
- Hospital operations news unrelated to specific drugs
- Patent filings (not expiry events)

INCLUDE if primarily about:
- Final FDA / EMA / CDSCO / NMPA / MHRA regulatory approvals
- Phase III or pivotal trial OUTCOMES (positive or negative)
- Acquisitions, mergers, or major licensing deals
- Fast Track, Breakthrough Therapy, or Orphan Drug designations
- First generic or biosimilar launches
- Patent expiry / market exclusivity events
- Label expansions or new indications

Return JSON:
{{
  "exclude": true,
  "reason": "one-line reason for the decision",
  "confidence": 0.85
}}"""


RELEVANCE_PROMPT = """\
Score the strategic relevance of this pharma article for a leadership team 
at a mid-to-large pharma company focused on Indian and global markets.

Article Title: {title}
Categories: {categories}
Extracted Entities: {entities}
Event Type: {event_type}

Scoring rubric:
- Business impact magnitude  (0-30 pts): Major approval/M&A=28-30 | Phase III outcome=20-25 | designation=12-18 | minor update=1-5
- Therapy area importance     (0-20 pts): Oncology/GLP-1/Gene Therapy/Rare Disease=18-20 | Cardio/Neuro/Immuno=12-16 | others=4-10
- Indian market relevance     (0-20 pts): Direct India CDSCO/Indian company action=18-20 | affects Indian generics=12-16 | global only=2-6
- Novelty / first-in-class    (0-15 pts): First-ever in class=13-15 | new indication=8-12 | line extension=3-6
- Regulatory significance     (0-15 pts): Final approval=13-15 | designation=7-10 | clinical outcome=5-8 | no regulatory=0-3

Return JSON:
{{
  "total_score": 74,
  "breakdown": {{
    "business_impact": 22,
    "therapy_importance": 18,
    "indian_market": 10,
    "novelty": 12,
    "regulatory": 12
  }},
  "score_rationale": "one sentence explaining the score"
}}"""


SUMMARIZATION_PROMPT = """\
Write a leadership-ready intelligence brief for this pharma event. The reader is a
pharma executive who wants the substance of the story, not a one-line headline.
Capture the "zest" of the news: what happened, the hard numbers, and why it matters.

Article Title: {title}
Article Text: {text}
Molecule: {molecule}
Company: {company}
Indication: {indication}
Event Type: {event_type}

Requirements:
- Write 4-6 sentences of substantive, analytical detail (NOT a single vague line).
- Lead with the most impactful fact (the actual outcome/decision), then add context.
- Always include: what happened, the molecule/company, the specific numbers
  (endpoints, %, p-values, deal values, sales figures, patient counts) and the
  strategic significance for the company and the market.
- Use precise, active voice. AVOID filler like "In a significant development",
  "It is worth noting", "notably".
- If Phase III/pivotal: state whether the primary endpoint was met, the key efficacy
  and safety results (with numbers), the comparator, and the therapy area.
- If an approval: state molecule, indication, geography, AND whether the product is
  already approved or marketed in OTHER geographies (e.g. "already approved by the FDA
  and EMA"); note competitive/first-in-class status if known.
- If M&A/licensing: state acquirer, target, deal value, the assets/portfolio gained,
  and the strategic rationale.
- Then provide 2-4 sharp analytical bullet points ("key_points") that a leadership
  team would care about (e.g. market size, cross-geography approval status, generic
  erosion risk, competitive implication, next catalyst/timeline).

Return JSON:
{{
  "summary": "4-6 sentence analytical brief with concrete numbers and significance.",
  "headline": "8-12 word factual headline",
  "key_metric": "single most important number/stat if present, else null",
  "key_points": [
    "Sharp analytical insight 1 (numbers/strategic implication)",
    "Sharp analytical insight 2 (e.g. approval status in other geographies)"
  ]
}}"""


DEDUPLICATION_PROMPT = """\
Determine if these two pharma articles are reporting on the SAME underlying pharma event.

Article A:
Title: {title_a}
Summary: {summary_a}
Entities: {entities_a}

Article B:
Title: {title_b}
Summary: {summary_b}
Entities: {entities_b}

Same event = same molecule + same company + same regulatory/clinical action at the same time.
Multiple sources covering the same FDA approval decision = SAME event.
Two different trials for the same molecule = DIFFERENT events.

Return JSON:
{{
  "is_duplicate": true,
  "confidence": 0.92,
  "canonical_title": "best title to represent the event (from A or B), or null if not duplicate"
}}"""
