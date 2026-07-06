# AI / LLM Reference

A complete reference of every system prompt, AI provider, and LLM model used in this project — what each one does, where it lives in the codebase, and how the pieces connect.

---

## Table of Contents

1. [AI Providers](#1-ai-providers)
2. [LLM Models](#2-llm-models)
3. [System Prompts](#3-system-prompts)
4. [End-to-End Data Flow](#4-end-to-end-data-flow)
5. [Rule-Based Fallbacks](#5-rule-based-fallbacks)
6. [Environment Variables & Configuration](#6-environment-variables--configuration)
7. [Quick Reference Table](#7-quick-reference-table)

---

## 1. AI Providers

Three AI providers are supported. They are accessed through the [`litellm`](https://github.com/BerriAI/litellm) universal proxy library (which handles request formatting and API key routing), with the exception of the native Anthropic adapter in the pharma pipeline.

| Provider | Auth Mechanism | Where It Is Used |
|---|---|---|
| **Groq** | `GROQ_API_KEY` env var or DB setting `groq_api_key` | Default for all crawl jobs, AI summaries, and consolidated reports |
| **OpenAI** | `OPENAI_API_KEY` env var | Fallback when no Groq key is present; also the default in `LLMConfig` |
| **Anthropic** | `ANTHROPIC_API_KEY` env var | Optional alternative exclusively for the pharma intelligence pipeline |

### Provider Selection Logic

**Crawl jobs, AI job summaries, consolidated reports**  
Read from DB setting `llm_provider` (default: `groq/llama-3.1-8b-instant`). If no Groq key exists, falls back to `gpt-4o-mini` with `OPENAI_API_KEY`.

```
// dashboard/engine.py — _make_openai_client()
model = llm_provider if groq_key else "gpt-4o-mini"
api_key = groq_key or openai_key
```

**Pharma intelligence pipeline**  
Controlled by the `PHARMA_LLM_PROVIDER` environment variable (`"openai"` or `"anthropic"`). Defaults to `"openai"` (which in practice means Groq via litellm, since the Groq key is what's configured).

```
// api/routers/intelligence.py — _make_llm_client()
provider = os.environ.get("PHARMA_LLM_PROVIDER", "openai").strip().lower()
if provider == "anthropic":
    return _make_anthropic_client()
return _make_openai_client()
```

---

## 2. LLM Models

| Model | Provider | Selectable? | Used In |
|---|---|---|---|
| `groq/llama-3.1-8b-instant` | Groq | Yes (default) | Crawl extraction, AI job summary, consolidated reports, pharma pipeline |
| `groq/llama-3.3-70b-versatile` | Groq | Yes | User-selectable in Settings UI |
| `groq/mixtral-8x7b-32768` | Groq | Yes | User-selectable in Settings UI |
| `gpt-4o-mini` | OpenAI | No (auto-fallback) | Jobs/consolidated reports when Groq key absent |
| `openai/gpt-4o` | OpenAI | No (code default) | Default value in `LLMConfig` dataclass; overridden at runtime |
| `claude-sonnet-4-5-20250929` | Anthropic | Via env var | Pharma pipeline when `PHARMA_LLM_PROVIDER=anthropic` |
| `$PHARMA_LLM_MODEL` | Anthropic | Via env var | Any Anthropic model; overrides the default above |

**Relevant files:**
- `crawl4ai/llm_config.py` — `LLMConfig` dataclass (default `openai/gpt-4o`)
- `api/models.py` — `SettingsResponse` (default `groq/llama-3.1-8b-instant`)
- `dashboard/pages/settings.py` — Streamlit settings UI (3 Groq options)
- `api/routers/settings.py` — REST settings endpoint

---

## 3. System Prompts

There are **11 distinct prompt contexts** across the project. Six pharma pipeline prompts share a single expert persona system prompt; the remaining five are inline in the engine and crawler code.

---

### 3.1 `SYSTEM_PHARMA_EXPERT` — Shared Pharma Persona

**File:** `crawl4ai/pharma_intelligence/prompts.py`

```
You are a senior pharma intelligence analyst with 20+ years of experience
in regulatory affairs, clinical development, and competitive intelligence.
You specialize in filtering signal from noise for leadership teams at pharmaceutical companies.
Your output is ALWAYS valid JSON. Never include text, markdown, or explanations outside the JSON object.
```

**Role:** Shared system prompt injected into every call made by the pharma intelligence pipeline (Layers 1–6). It anchors the LLM's domain knowledge, output format (always valid JSON), and tone across all pipeline steps.

**Used by:** `EntityExtractor`, `ArticleClassifier`, `ExclusionFilter`, `RelevanceScorer`, `LeadershipSummarizer`, `Deduplicator`

---

### 3.2 `EXTRACTION_PROMPT` — Layer 1: Entity Extraction

**File:** `crawl4ai/pharma_intelligence/prompts.py` → called from `crawl4ai/pharma_intelligence/extraction.py`

**Template variables:** `{title}`, `{text}`

**What it does:** Extracts 9 structured pharma entities from raw article text:

| Field | Description |
|---|---|
| `molecule` | Primary drug INN name |
| `brand_name` | Brand name if mentioned |
| `company` | Primary pharma company |
| `indication` | Disease / medical condition |
| `trial_phase` | Phase I / II / III / IV |
| `geography` | Country or region |
| `regulatory_body` | FDA / EMA / CDSCO / NMPA / MHRA / other |
| `event_type` | One of: approval, clinical_outcome, ma, licensing, discontinuation, label_expansion, designation, generic_launch, manufacturing, patent, conference, preclinical, other |
| `deal_value` | Deal value in USD millions |

**Downstream effect:** The `event_type` and `regulatory_body` fields feed directly into the classifier, filter, scorer, and formatter. If this step is wrong, every downstream layer is affected.

**Fallback:** `EntityExtractor._extract_with_rules()` — regex patterns for regulatory body, trial phase, and event type.

---

### 3.3 `CLASSIFICATION_PROMPT` — Layer 2: Multi-label Classification

**File:** `crawl4ai/pharma_intelligence/prompts.py` → called from `crawl4ai/pharma_intelligence/classifier.py`

**Template variables:** `{title}`, `{text}` (truncated to 2000 chars), `{entities}`

**What it does:** Assigns 3–5 categories to an article from a fixed taxonomy:

```
REGULATORY:   FDA Approval | EMA Approval | CDSCO Approval | NMPA Approval | MHRA Approval | Other Regulatory Approval
CLINICAL:     Phase III Success | Phase III Failure | Clinical Trial
BUSINESS:     M&A Activity | Licensing Deal | Manufacturing | Pipeline Update | Discontinuation
DESIGNATIONS: Fast Track Designation | Breakthrough Therapy | Orphan Drug Designation
PRODUCT:      First Generic Launch | Biosimilar | ANDA Approval | Patent Expiry | Label Expansion
THERAPY AREA: Oncology | GLP-1 / Obesity | Cardiovascular | Neurology | Immunology |
              Infectious Disease | Rare Disease | Gene Therapy | Diabetes | Respiratory
MARKET:       Indian Market | Competitive Intelligence
```

Returns `categories[]`, `primary_category`, and `therapy_area`.

**Downstream effect:** Categories determine KPI weights in the scorer, grouping in the email formatter, and which articles are forced into "Key Highlights" (e.g. any `FDA Approval`, `Gene Therapy`, `Orphan Drug Designation`).

**Fallback:** `ArticleClassifier._classify_with_rules()` — 30+ compiled regex patterns over title + text.

---

### 3.4 `EXCLUSION_PROMPT` — Layer 3: Noise / Demotion Filter

**File:** `crawl4ai/pharma_intelligence/prompts.py` → called from `crawl4ai/pharma_intelligence/filter.py`

**Template variables:** `{title}`, `{text}` (truncated to 2000 chars), `{event_type}`

**What it does:** Determines if an article should be demoted from the leadership brief. Articles are demoted (not deleted — never-drop policy) if they are primarily about:
- IND or CTA filings
- Phase I / II trial initiations or enrollment
- Conference presentations, poster abstracts
- Preclinical / animal / in vitro data
- Filing acceptance for review (not the decision itself)
- Priority review designation (not final approval)

Returns `{ "exclude": bool, "reason": string, "confidence": float }`.

**Important:** Confidence below 0.65 defaults to **include** (conservative). Hard rule-based checks run first, before the LLM is called.

**Downstream effect:** Demoted articles move to the "Other News" section of the brief instead of the main highlights. The `demoted` flag and `demotion_reason` are stored in the result.

**Fallback:** Hard-coded ontology patterns in `crawl4ai/pharma_intelligence/ontology.py` (`is_hard_excluded`, `has_strong_include_signal`).

---

### 3.5 `RELEVANCE_PROMPT` — Layer 4: KPI-Weighted Relevance Scoring

**File:** `crawl4ai/pharma_intelligence/prompts.py` → called from `crawl4ai/pharma_intelligence/scorer.py`

**Template variables:** `{title}`, `{categories}`, `{entities}`, `{event_type}`

**What it does:** Scores an article 0–100 across 5 dimensions:

| Dimension | Max Points | High-value examples |
|---|---|---|
| Business impact magnitude | 30 | Major approval/M&A = 28–30 |
| Therapy area importance | 20 | Oncology/GLP-1/Gene Therapy = 18–20 |
| Indian market relevance | 20 | Direct CDSCO/Indian company action = 18–20 |
| Novelty / first-in-class | 15 | First-ever in class = 13–15 |
| Regulatory significance | 15 | Final approval = 13–15 |

Returns `total_score`, `breakdown` dict, and `score_rationale` (one sentence).

**Downstream effect:**
- `is_key_highlight` flag set when score ≥ threshold (default 60) OR article is in always-highlight categories
- Articles with `total_score < min_score_threshold` (default 10) are demoted
- All results are sorted: key highlights first, then by descending score

**Fallback:** `RelevanceScorer._score_with_rules()` — combines KPI weights from `ontology.KPI_WEIGHTS` with category-specific point values.

---

### 3.6 `SUMMARIZATION_PROMPT` — Layer 5: Leadership Summary

**File:** `crawl4ai/pharma_intelligence/prompts.py` → called from `crawl4ai/pharma_intelligence/summarizer.py`

**Template variables:** `{title}`, `{text}` (truncated to 3500 chars), `{molecule}`, `{company}`, `{indication}`, `{event_type}`

**What it does:** Writes a leadership-ready intelligence brief for each article with:
- **4–6 sentences** of substantive, analytical detail (not a one-liner)
- Hard numbers: endpoints, p-values, percentages, deal values, patient counts
- Strategic context: competitive position, geography, cross-approval status
- **2–4 bullet key points** for executives (market size, generic risk, next catalyst, etc.)
- An 8–12 word factual headline
- A single `key_metric` (most important number/stat)

Returns `{ "summary": string, "headline": string, "key_metric": string|null, "key_points": string[] }`.

**Downstream effect:** These four fields are what end up in the leadership email brief and the pharma intelligence report. This is the most user-visible LLM output in the whole system.

**Fallback:** `LeadershipSummarizer._summarize_with_rules()` — extracts lead sentences, derives key points from entities and numerical patterns in the text.

---

### 3.7 `DEDUPLICATION_PROMPT` — Duplicate Event Clustering

**File:** `crawl4ai/pharma_intelligence/prompts.py` → called from `crawl4ai/pharma_intelligence/deduplicator.py`

**Template variables:** `{title_a}`, `{summary_a}`, `{entities_a}`, `{title_b}`, `{summary_b}`, `{entities_b}`

**What it does:** AI-verifies whether two articles report the **same underlying pharma event**. Only called when heuristics are ambiguous (entity fingerprint match with ≥2 shared fields). Same event = same molecule + company + regulatory/clinical action at the same time.

Returns `{ "is_duplicate": bool, "confidence": float, "canonical_title": string|null }`.

**Downstream effect:** Duplicate articles are merged into a single card in the brief. The richer article (more entity fields filled + longer summary) becomes the primary; `sources[]` lists all source publications. `is_consolidated: true` and `source_count` are set on the merged item.

**Pre-filter (no LLM needed):** Jaccard title similarity ≥ 0.55 triggers automatic clustering without calling the LLM.

---

### 3.8 Inline: Web Crawl Extraction System Prompt

**File:** `crawl4ai/extraction/llm_extraction.py` → `_build_system_prompt()`

**System prompt (dynamically built):**
```
You are a precise data extraction assistant.
Extract information from the provided web page content.
Return the extracted data as a JSON array of objects matching this schema:
{ ... JSON schema ... }
Return ONLY valid JSON – no commentary, no markdown fences.
```

**User prompt:** The raw crawled HTML/markdown content, truncated to `content_length_limit` (default 12,000 chars), prefixed with the job's extraction instruction.

**Default extraction instruction (from `engine.py`):**
```
The current date and time is {now_str} IST (Asia/Kolkata).
Extract ONLY actual news articles published within the LAST 24 HOURS,
i.e. on or after {cutoff_str} IST.
DO NOT include older articles.
Ignore ads, promotions, newsletters, events, navigation links, and category labels.
For each article include: title, source, category, summary, time_ago,
and published_date (the exact date and time shown on the article, if visible).
Return a JSON array containing only articles from the last 24 hours.
```

**What it does:** Converts raw scraped HTML into a structured JSON array of articles. This is the very first LLM step in every crawl job. The 24h window is enforced both here (LLM instruction) and by a post-filter in `engine.py` (rule-based safety net).

**Provider:** Groq (`llm_provider` setting), temperature = 0, max_tokens = 4000.

---

### 3.9 Inline: AI Job Summary (`summarize_with_ai`)

**File:** `dashboard/engine.py` — `_execute_job()`

**System prompt:**
```
You are a news analyst. Write clear, concise executive summaries.
```

**User prompt:**
```
Based on these {article_count} scraped articles, write a concise 2-3 sentence
executive summary covering the main themes and key topics:

- Title 1: summary 1
- Title 2: summary 2
...
```

**What it does:** Optional per-job feature (`summarize_with_ai: true` in job config). After all articles are extracted, generates a 2–3 sentence executive summary over the top 25 articles and injects it into the email (`EmailOutput.ai_summary`) and PDF report (`PDFReportOutput.ai_summary`).

**Provider:** Groq (`llm_provider` setting), temperature = 0.3, max_tokens = 200.

**Trigger:** Only runs when `config["summarize_with_ai"] == True` AND `article_count > 0` AND a Groq key is present.

---

### 3.10 Inline: Consolidated Report System Prompt

**File:** `dashboard/consolidated.py` — `generate_and_send_consolidated_report()`

**System prompt:**
```
You are a professional analyst. Write clear, well-structured
consolidated reports from news and data collections.
Use the exact section headers requested.
```

**User prompt (weekly/monthly):**
```
You are a professional analyst. Below are {N} articles/items collected
from '{url}' over the past {weekly|monthly} period ({date_range}).

Create a comprehensive consolidated {period} report with these sections:
1. **Executive Summary** (3-4 sentences covering the dominant themes)
2. **Key Trends & Patterns** (3-5 bullet points of recurring themes)
3. **Notable Headlines** (top 5-7 most significant items with brief context)
4. **Overall Assessment** (1-2 closing sentences about the period)

Articles collected:
1. Title [Source] (Category) — summary
2. ...
```

**What it does:** Generates a weekly or monthly digest across all crawl runs for a schedule. Capped at 100 articles to stay within token limits. The output is rendered into a styled HTML email and sent to the schedule's recipients.

**Provider:** Groq (`llm_provider` setting), temperature = 0.3, max_tokens = 800.

**Trigger:** Run by the scheduler when `consolidated_frequency` is set on a schedule (`"weekly"` or `"monthly"`) and the cooldown since `consolidated_last_sent` has elapsed.

---

### 3.11 Inline: LLM Noise Filter

**File:** `crawl4ai/deep_crawler.py` — `_llm_filter_articles()`

**No separate system prompt** — uses the `LLMExtractionStrategy` directly.

**Prompt (injected as extraction instruction):**
```
Below is a numbered list of items extracted from a news website.
Some are REAL NEWS ARTICLES, others are noise (navigation labels,
category headers, newsletter promos, event announcements, ads,
awards listings, social media CTAs, or section titles).

Return ONLY a JSON array of the numbers (integers) that are REAL NEWS ARTICLES.
Exclude anything that is not an actual news story.

Items:
1. Title A
2. Title B
...

Response format: [1, 3, 5, 7, ...]
```

**What it does:** Post-extraction noise filter. After the main `LLMExtractionStrategy` extracts articles, this secondary LLM call reviews only the titles and returns the indices of real news articles. Removes navigation labels, promo blocks, and event listings that slipped through the schema-based extraction.

**Skipped if:** ≤ 3 articles extracted (not worth the API call). Falls back to the unfiltered list on any error.

---

## 4. End-to-End Data Flow

```
Web URL
  │
  ▼
[deep_crawl]
  Browser scrapes listing + inner pages, returns combined markdown/HTML.
  │
  ▼
[LLMExtractionStrategy]  ←── Prompt 3.8 (extraction instruction)
  Provider: Groq llama-3.1-8b-instant
  Temperature: 0  |  Max tokens: 4000  |  Content limit: 12,000 chars
  Output: JSON array [ { title, source, category, summary, time_ago, published_date } ]
  │
  ▼
[LLM Noise Filter]  ←── Prompt 3.11 (deep_crawler.py)
  Same provider/model. Sends titles only, returns keep-indices.
  │
  ▼
[24h Post-Filter]
  Rule-based. Drops articles older than 24h using published_date / time_ago.
  │
  ▼
[AI Job Summary - optional]  ←── Prompt 3.9 (engine.py)
  Provider: Groq  |  Temperature: 0.3  |  Max tokens: 200
  Injects 2-3 sentence summary into email + PDF outputs.
  │
  ├──► Articles stored in DB  (jobs.extracted_articles JSONB)
  │
  ▼
[PharmaPipeline]  POST /api/intelligence/process
  Provider selected by PHARMA_LLM_PROVIDER env var
  (default: Groq via litellm, fallback: Anthropic native)
  Temperature: 0.1  |  Max tokens: 2048
  │
  ├── Layer 1: [EntityExtractor]  ←── Prompt 3.1 (system) + 3.2 (user)
  │     → molecule, company, indication, trial_phase, event_type, geography...
  │
  ├── Layer 2: [ArticleClassifier]  ←── Prompt 3.1 (system) + 3.3 (user)
  │     → categories[], primary_category, therapy_area
  │
  ├── Layer 3: [ExclusionFilter]  ←── Prompt 3.1 (system) + 3.4 (user)
  │     → demoted: bool, demotion_reason (never deleted — never-drop policy)
  │
  ├── Layer 4: [RelevanceScorer]  ←── Prompt 3.1 (system) + 3.5 (user)
  │     → total_score (0–100), is_key_highlight, score_breakdown
  │
  ├── [Deduplicator]  ←── Prompt 3.1 (system) + 3.7 (user)  [ambiguous pairs only]
  │     → clusters articles → merged cards with sources[]
  │
  └── Layer 5: [LeadershipSummarizer]  ←── Prompt 3.1 (system) + 3.6 (user)
        → summary (4-6 sentences), headline, key_metric, key_points[]
              │
              ▼
        [PharmaEmailFormatter]
        Sorted output: Key Highlights first → by score → Other News
              │
              ▼
        Stored in pharma_results (PostgreSQL)
              │
              ▼
[Consolidated Report]  ←── Prompt 3.10 (consolidated.py)
  Provider: Groq  |  Temperature: 0.3  |  Max tokens: 800
  Weekly or monthly digest per schedule → HTML email sent to recipients
```

---

## 5. Rule-Based Fallbacks

Every LLM call has a deterministic fallback so the system runs without API keys. Fallbacks are triggered when `llm_client is None` (no key configured) or on any exception from the LLM call.

| Layer | LLM Path | Fallback Path |
|---|---|---|
| Entity Extraction | `EntityExtractor._extract_with_llm()` | `_extract_with_rules()` — regex for regulatory body, trial phase, event type |
| Classification | `ArticleClassifier._classify_with_llm()` | `_classify_with_rules()` — 30+ compiled regex patterns |
| Exclusion Filter | `ExclusionFilter._ai_exclude()` | Ontology hard-include/hard-exclude patterns, then default include |
| Relevance Scoring | `RelevanceScorer._score_with_llm()` | `_score_with_rules()` — KPI weights × category point table |
| Deduplication | `Deduplicator._ai_verify_duplicate()` | Jaccard title similarity + entity fingerprint matching |
| Summarization | `LeadershipSummarizer._summarize_with_llm()` | Lead sentence extraction + heuristic key point derivation |
| Web Crawl Extraction | `LLMExtractionStrategy.aextract()` | Raises `ValueError` (LLM is required for this step) |
| Noise Filter | `_llm_filter_articles()` | Returns unfiltered article list |
| AI Job Summary | litellm call in `_execute_job()` | Skipped silently (summary field left empty) |
| Consolidated Report | litellm call in `consolidated.py` | Returns early, no email sent |

---

## 6. Environment Variables & Configuration

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | — | Groq API key (primary LLM provider) |
| `OPENAI_API_KEY` | — | OpenAI API key (fallback) |
| `ANTHROPIC_API_KEY` | — | Anthropic API key (pharma pipeline alternative) |
| `PHARMA_LLM_PROVIDER` | `"openai"` | Selects pharma pipeline provider: `"openai"` (uses Groq via litellm) or `"anthropic"` |
| `PHARMA_LLM_MODEL` | `"claude-sonnet-4-5-20250929"` | Anthropic model override (only applies when `PHARMA_LLM_PROVIDER=anthropic`). Verify this model is available to your Anthropic account/key — an invalid name here causes every pipeline layer to silently fall back to rule-based output (now logged as a warning; see `api/routers/intelligence.py`). |

### Database Settings (override env vars at runtime)

Stored in the `settings` table, editable via the Settings page or `PUT /api/settings`:

| Key | Default | Purpose |
|---|---|---|
| `groq_api_key` | `""` | Groq API key (takes priority over env var) |
| `llm_provider` | `"groq/llama-3.1-8b-instant"` | Model for crawl extraction, AI summary, consolidated reports |
| `default_max_scrolls` | `10` | Default scroll depth for new jobs |
| `default_max_inner_pages` | `5` | Default inner page follow depth |
| `default_content_limit` | `12000` | Max chars passed to LLM extraction |

### Relevant Source Files

| File | Role |
|---|---|
| `crawl4ai/llm_config.py` | `LLMConfig` dataclass — provider + api_token + base_url |
| `crawl4ai/extraction/llm_extraction.py` | `LLMExtractionStrategy` — web crawl extraction via litellm |
| `crawl4ai/pharma_intelligence/prompts.py` | All 7 pharma prompt templates |
| `crawl4ai/pharma_intelligence/extraction.py` | Layer 1 — entity extractor |
| `crawl4ai/pharma_intelligence/classifier.py` | Layer 2 — multi-label classifier |
| `crawl4ai/pharma_intelligence/filter.py` | Layer 3 — exclusion/demotion filter |
| `crawl4ai/pharma_intelligence/scorer.py` | Layer 4 — KPI relevance scorer |
| `crawl4ai/pharma_intelligence/summarizer.py` | Layer 5 — leadership summarizer |
| `crawl4ai/pharma_intelligence/deduplicator.py` | Duplicate event clustering |
| `crawl4ai/pharma_intelligence/pipeline.py` | `PharmaPipeline` — orchestrates all layers |
| `crawl4ai/deep_crawler.py` | `_llm_filter_articles()` — noise filter after extraction |
| `dashboard/engine.py` | Job execution, AI summary, provider selection |
| `dashboard/consolidated.py` | Weekly/monthly consolidated report generation |
| `api/routers/intelligence.py` | Pharma pipeline API + LLM client factory |
| `api/routers/settings.py` | Settings REST endpoint |
| `dashboard/pages/settings.py` | Streamlit settings UI |

---

## 7. Quick Reference Table

| # | Prompt | File | System Message Summary | Provider | Model | Temperature | Max Tokens |
|---|---|---|---|---|---|---|---|
| 3.1 | `SYSTEM_PHARMA_EXPERT` (shared) | `prompts.py` | Senior pharma analyst, always return valid JSON | OpenAI or Anthropic | Configurable | 0.1 | 2048 |
| 3.2 | `EXTRACTION_PROMPT` | `prompts.py` → `extraction.py` | Extract 9 pharma entity fields | Same | Same | 0.1 | 2048 |
| 3.3 | `CLASSIFICATION_PROMPT` | `prompts.py` → `classifier.py` | Assign 3–5 categories from taxonomy | Same | Same | 0.1 | 2048 |
| 3.4 | `EXCLUSION_PROMPT` | `prompts.py` → `filter.py` | Flag low-value articles for demotion | Same | Same | 0.1 | 2048 |
| 3.5 | `RELEVANCE_PROMPT` | `prompts.py` → `scorer.py` | Score 0–100 across 5 KPI dimensions | Same | Same | 0.1 | 2048 |
| 3.6 | `SUMMARIZATION_PROMPT` | `prompts.py` → `summarizer.py` | Write 4–6 sentence leadership brief | Same | Same | 0.1 | 2048 |
| 3.7 | `DEDUPLICATION_PROMPT` | `prompts.py` → `deduplicator.py` | Verify if two articles = same event | Same | Same | 0.1 | 2048 |
| 3.8 | Web crawl extraction | `llm_extraction.py` | Precise data extraction assistant | Groq | `llm_provider` setting | 0 | 4000 |
| 3.9 | AI job summary | `engine.py` | News analyst, concise executive summaries | Groq | `llm_provider` setting | 0.3 | 200 |
| 3.10 | Consolidated report | `consolidated.py` | Professional analyst, structured reports | Groq | `llm_provider` setting | 0.3 | 800 |
| 3.11 | LLM noise filter | `deep_crawler.py` | (No separate system prompt — inline) | Groq | `llm_provider` setting | 0 | 4000 |
