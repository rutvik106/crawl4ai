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
  "counterparties": ["for a deal/M&A/licensing/collaboration, the companies involved, e.g. [\"Pfizer\", \"Innovent\"]; else []"],
  "transaction_type": "one of: M&A | Acquisition | Licensing | Collaboration | Partnership | null",
  "indication": "disease or medical condition being treated",
  "trial_phase": "Phase I / Phase II / Phase III / Phase IV / null",
  "geography": "country or region where the event occurred",
  "regulatory_body": "FDA / EMA / CDSCO / NMPA / MHRA / other / null",
  "event_type": "one of: approval | clinical_outcome | ma | licensing | discontinuation | label_expansion | designation | generic_launch | manufacturing | patent | conference | preclinical | other",
  "regulatory_status": "one of: final_approval | label_expansion | positive_recommendation | priority_review | filing_acceptance | designation | launch | exclusivity | withdrawal | trial_outcome | not_applicable",
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
REGULATORY MILESTONES: Priority Review | Regulatory Filing | Positive Regulatory Recommendation | Market Withdrawal
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
- A molecule merely ADVANCING/PROGRESSING/ENTERING a clinical phase (e.g. "to
  Phase 2b/Phase III") WITHOUT reported meaningful clinical data
- Trial commentary that does NOT disclose substantive data (e.g. "CEO discusses
  trial results without disclosing data")
- Conference presentations, poster abstracts
- UPCOMING conference presentation announcements ("to present ... at Congress
  2026"). Cover the later item only once results are actually presented/released
- Preclinical, in vitro, or animal study data
- Filing acceptance for review (not the decision itself)
- Routine filing acceptance without additional strategic evidence
- Early discovery or research stage news
- Preliminary regulatory interactions / study-design or scientific advice
  (e.g. "receives multi-agency advice on registrational study design") — no
  material development outcome
- Manufacturing / capacity expansions, spray-drying, or facility/site
  developments (incl. acquisitions of a manufacturing site)
- AI-based collaborations UNLESS directly linked to a specific drug-development
  asset or pipeline value
- Management / leadership / board appointments and departures
- Market forecast / market-size reports
- Webinar or conference PARTICIPATION announcements ("to join a webinar")
- Hospital operations news unrelated to specific drugs
- Patent filings (not expiry events)

INCLUDE if primarily about:
- Final FDA / EMA / CDSCO / NMPA / MHRA regulatory approvals
- Positive regulatory recommendations (e.g. CHMP recommends X) — a significant
  regulatory milestone
- Phase IIb / Phase III or later-stage OUTCOMES with meaningful reported data
  (positive or negative)
- Label expansions or new indications
- Major mergers, acquisitions, licensing, partnership, or asset transactions
  involving pipeline or commercial products
- Fast Track, Breakthrough Therapy, or Orphan Drug designations
- First generic or biosimilar launches; important commercial launches
- Patent expiry / market exclusivity events
- Priority Review backed by strong late-stage evidence and exceptional strategic relevance

Return JSON:
{{
  "exclude": true,
  "reason": "one-line reason for the decision",
  "confidence": 0.85
}}"""


RELEVANCE_PROMPT = """\
Assess whether this article belongs in "Key Highlights" or "Other News" for a
Daily Bites brief read by pharma leadership. High recall is handled elsewhere:
every valid article is retained, so this task is prioritization, not exclusion.

Article Title: {title}
Article Text (excerpt): {text}
Categories: {categories}
Extracted Entities: {entities}
Event Type: {event_type}

Evaluate five dimensions (total 0-{total_max}):
- Event maturity (0-{event_maturity_max}): final approval, meaningful label
  expansion, pivotal outcome, completed strategic transaction, or withdrawal
  outranks filing, Priority Review, designation, formulation update, and early
  research.
- Clinical/evidence strength (0-{evidence_strength_max}): pivotal endpoints and
  quantified outcomes outrank unquantified or early-stage evidence.
- Strategic significance (0-{strategic_significance_max}): first/only therapy,
  standard-of-care potential, major unmet need, material competitive disruption,
  or portfolio transformation.
- Commercial implications (0-{commercial_implications_max}): credible market
  expansion, revenue exposure, exclusivity, pricing/patent impact, or mature
  assets. Deal headline value alone is not sufficient, especially for
  preclinical/early-stage programs.
- India/Torrent relevance (0-{india_torrent_relevance_max}): direct Indian
  market impact, Torrent relevance, or a material Indian-company action. Indian
  involvement alone is not sufficient.

Decision guardrails:
- Emphasize: regulatory approvals AND positive regulatory recommendations
  (e.g. CHMP), significant Phase IIb/Phase III data, label expansions, major
  licensing/acquisition/partnership/asset transactions, important commercial
  launches, and meaningful clinical/regulatory outcomes backed by robust data.
- A positive regulatory recommendation (CHMP recommends / adopts a positive
  opinion) is a significant milestone and normally qualifies as a Key Highlight.
- Routine generic/tentative approvals normally belong in Other News unless they
  are first-generic, exclusive, or commercially/competitively material.
- Priority Review, filing acceptance, and designations normally belong in Other
  News unless several strong amplifiers make the event strategically exceptional.
- Do not call a review milestone a final approval.
- Do not promote every FDA/EMA event, Indian-company item, M&A, or licensing deal.
- A Key Highlight should normally score at least {key_highlight_threshold} (out
  of {total_max}) and have a concrete rationale.

Return JSON:
{{
  "total_score": 74,
  "breakdown": {{
    "event_maturity": 26,
    "evidence_strength": 14,
    "strategic_significance": 16,
    "commercial_implications": 10,
    "india_torrent_relevance": 8
  }},
  "is_key_highlight": true,
  "score_rationale": "one sentence naming the event maturity and the strongest strategic reason",
  "classification_confidence": 0.86
}}"""


SUMMARIZATION_PROMPT = """\
Write a concise Daily Bites-style intelligence brief for this pharma event. The
reader wants the substance of the story, not a generic headline or padded analysis.

Article Title: {title}
Article Text: {text}
Molecule: {molecule}
Company: {company}
Indication: {indication}
Event Type: {event_type}

Requirements:
- Write ONE tight paragraph of 2-3 sentences (about 3 lines max). Be concise —
  the description is the most important content and must not run long.
- Return summary prose only in the summary field. Do not include the asset/molecule
  label, a source label, a URL, markdown, bullets, or "Read the full article";
  those are added deterministically by the report formatter.
- Integrate everything into a flowing narrative. Do NOT emit labelled fields such
  as "Indication:", "Event:", or "Regulatory Status:" inside the summary text.
- Follow this sequence where the source supports it: event/update; quantified
  evidence; strategic/commercial impact.
- Never invent a field. Use null when the source does not support it.
- Lead with the actual outcome/decision and clearly distinguish final approval from
  filing acceptance, Priority Review, recommendation, designation, or launch.
- Include concrete endpoints, percentages, deal values, sales, or patient counts
  when present in the source.
- Use precise, active voice. AVOID filler like "In a significant development",
  "It is worth noting", "notably".
- For approvals/recommendations backed by a pivotal study: STATE that the decision
  is based on a Phase III (or Phase IIb) trial, NAME the trial, give its key
  efficacy/safety result (with numbers), and — most importantly — the KEY
  DIFFERENTIATING factor versus existing/standard-of-care therapies (why this was
  approved over existing options and how it compared). Keep benchmarks grounded in
  the source article.
- If an approval: state molecule, indication, geography, AND include one line on
  the product's existing regulatory footprint / geographical approvals across major
  regions (e.g. "already approved by the FDA and EMA"); note first-in-class status
  if known.
- If M&A/licensing/collaboration/acquisition/partnership: state the companies
  involved, the deal value whenever publicly available, the assets/portfolio
  gained, and the rationale.
- Keep implications grounded in the article; do not turn assumptions into facts.

Match the tone, density, and structure of these reference Daily Bites entries
(written by the client). Do not copy their content - only their style:

Example 1 (final approval backed by pivotal evidence):
"The FDA has approved AstraZeneca's Imfinzi Durvalumab with BCG for BCG-naive,
high-risk non-muscle-invasive bladder cancer. The Phase III POTOMAC trial
showed a 32% reduction in recurrence, progression, or death versus BCG alone.
This marks the first new therapy in over 30 years for this setting, offering
improved disease-free survival with no new safety concerns. The approval
signals a potential shift in standard care for high-risk NMIBC patients."

Example 2 (Priority Review - not yet approved; evidence + designations, no
overstated status):
"Zydus Therapeutics received US-FDA Priority Review for its NDA, supported by
the Phase IIb/III EPICS-III trial showing a 56.7% versus 9.8% biochemical
response, in primary biliary cholangitis (PBC). The therapy is not yet
approved; it holds Orphan Drug and Fast Track designations for this rare
autoimmune liver disease."

Example 3 (licensing deal - deal value plus assets plus strategic rationale):
"Pfizer and Innovent Biologics signed a global licensing deal worth up to
$10.5 billion to develop 12 early-stage cancer therapies. Innovent will lead
early development, with Pfizer taking over global trials and commercialization
under a tiered structure. The deal includes $650 million upfront and
significant milestone-based payments, highlighting growing global interest in
China's biotech innovation pipeline."

Example 4 (India-market strategic entry - geography and unmet-need framing):
"Torrent Pharma plans India entry of resmetirom, a US-approved, first-in-class
MASH therapy, following patent expiry, and is currently conducting Phase III
trials in India with a potential launch 12-18 months after expiry. The therapy
is already FDA-approved for non-cirrhotic MASH with fibrosis; no innovative
therapies are currently available in India, indicating strong unmet need."

Return JSON:
{{
  "summary": "tight 2-3 sentence analytical brief (~3 lines max)",
  "headline": "8-12 word factual headline",
  "key_metric": "single most important number/stat if present, else null",
  "event_update": "what happened, including molecule/company, or null",
  "evidence": "key quantified clinical/business evidence, or null",
  "regulatory_status": "exact status and geography, or null",
  "clinical_stage": "trial/development stage and next catalyst, or null",
  "strategic_significance": "grounded competitive or treatment significance, or null",
  "commercial_implications": "grounded market, launch, exclusivity, pricing, sales, or deal implication, or null",
  "key_points": [
    "optional grounded analytical insight retained for API compatibility"
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
