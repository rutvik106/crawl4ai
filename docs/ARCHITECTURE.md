# Crawl4AI Architecture

Six Mermaid diagrams that cover the essential architecture of the project.

---

## 1. System Context

Who/what is involved, how the pieces are deployed, and how they connect at a high level.

```mermaid
flowchart TD
    subgraph Clients
        BROWSER[Web Browser / API Client]
    end

    subgraph AppLayer["Application Layer"]
        API["FastAPI\n(api/ — uvicorn)"]
        DASH["Streamlit Dashboard\n(dashboard/app.py)"]
        SCHED["APScheduler\n(dashboard/scheduler.py)"]
        ENGINE["Job Engine\n(dashboard/engine.py)"]
    end

    subgraph CrawlerLib["crawl4ai Library"]
        CRAWLER["AsyncWebCrawler\nasync_webcrawler.py"]
        DEEP["deep_crawl()\ndeep_crawler.py"]
        PHARMA["Pharma Intelligence\npipeline.py"]
        OUTPUTS["Output Backends\noutput/"]
    end

    subgraph External
        PW["Playwright / Chromium\n(headless browser)"]
        LLM["LLM Providers\n(Groq / OpenAI / Ollama\nvia litellm)"]
        PG["PostgreSQL\n(Neon.tech)"]
        BLOB["Vercel Blob Storage"]
        SMTP["SMTP / Email"]
    end

    BROWSER -->|"REST /api/*"| API
    BROWSER -->|"Streamlit UI"| DASH
    API --> ENGINE
    DASH --> ENGINE
    SCHED -->|"cron fire"| ENGINE
    ENGINE --> CRAWLER
    CRAWLER --> DEEP
    ENGINE --> PHARMA
    DEEP --> PW
    CRAWLER --> LLM
    PHARMA --> LLM
    ENGINE --> OUTPUTS
    OUTPUTS --> BLOB
    OUTPUTS --> SMTP
    API --> PG
    DASH --> PG
    SCHED --> PG
    ENGINE --> PG
```

---

## 2. Database Entity-Relationship

All PostgreSQL tables, columns, and foreign-key relationships.

```mermaid
erDiagram
    USERS {
        serial      id            PK
        text        username      UK
        text        email         UK
        text        password_hash
        text        role
        integer     created_by    FK
        boolean     is_active
        timestamptz created_at
        timestamptz expires_at
    }

    JOBS {
        text        id            PK
        text        name
        text        url
        jsonb       config
        text        status
        timestamptz created_at
        timestamptz started_at
        timestamptz finished_at
        integer     article_count
        text        error
        text        output_dir
        jsonb       blob_urls
        integer     user_id       FK
        integer     schedule_id   FK
        jsonb       extracted_articles
        text        batch_id
    }

    SCHEDULES {
        serial      id            PK
        text        job_name
        text        url
        jsonb       config
        text        cron
        text        recipients
        integer     enabled
        timestamptz last_run
        timestamptz next_run
        timestamptz created_at
        integer     user_id       FK
        text        consolidated_frequency
        timestamptz consolidated_last_sent
        text        batch_id
    }

    SETTINGS {
        text key    PK
        text value
    }

    PHARMA_RESULTS {
        text        date_key    PK
        jsonb       result
        timestamptz created_at
    }

    PHARMA_CONFIG {
        integer     id          PK
        jsonb       config
        timestamptz updated_at
    }

    USERS ||--o{ USERS       : "created_by"
    USERS ||--o{ JOBS        : "owns"
    USERS ||--o{ SCHEDULES   : "owns"
    SCHEDULES ||--o{ JOBS    : "spawns"
```

---

## 3. Core Crawler Class Model

The key classes in the `crawl4ai/` library, their composition, and the strategy/plugin hierarchy.

```mermaid
classDiagram
    direction TB

    class AsyncWebCrawler {
        +BrowserConfig browser_config
        +HookRegistry hooks
        +_sessions: Dict[str, Page]
        +arun(url, config) CrawlResult
        +arun_many(urls, config) List[CrawlResult]
        -_ensure_browser()
        -_get_page(config) Page
        -_fetch_html(url, config) str
        -_run_extraction(strategy, url, content) str
    }

    class AdaptiveCrawler {
        +AsyncWebCrawler crawler
        +float target_confidence
        +int max_pages
        +digest(url, query, config) AdaptiveResult
        -_compute_relevance(text, terms) float
        -_compute_confidence(terms) float
    }

    class BrowserConfig {
        +headless: bool
        +stealth_mode: bool
        +simulate_human: bool
        +block_images: bool
        +login: LoginConfig
        +cookies: List[Dict]
    }

    class CrawlerRunConfig {
        +cache_mode: CacheMode
        +extraction_strategy: ExtractionStrategy
        +markdown_generator: DefaultMarkdownGenerator
        +css_selector: str
        +js_code: List[str]
        +output: List[OutputBackend]
        +clone() CrawlerRunConfig
    }

    class DeepCrawlConfig {
        +scroll: bool
        +max_scrolls: int
        +follow_links: bool
        +paginate: bool
        +max_inner_pages: int
        +smart_filter: bool
    }

    class HookRegistry {
        +on_browser_created
        +on_page_loaded
        +after_js_execution
        +before_return_html
        +on_error
        +trigger(event, page, ctx)
    }

    class ExtractionStrategy {
        <<abstract>>
        +extract(url, html) str
        +aextract(url, html) str
    }

    class LLMExtractionStrategy {
        +LLMConfig llm_config
        +schema: Dict
        +instruction: str
        +aextract(url, html) str
    }

    class JsonCssExtractionStrategy {
        +schema: Dict
        +extract(url, html) str
        +generate_schema(html, llm_config)$
    }

    class ContentFilterStrategy {
        <<abstract>>
        +filter(text) str
    }

    class PruningContentFilter {
        +threshold: float
        +filter(text) str
    }

    class BM25ContentFilter {
        +query: str
        +bm25_threshold: float
        +filter(text) str
    }

    class DefaultMarkdownGenerator {
        +ContentFilterStrategy content_filter
        +convert(html) MarkdownResult
    }

    class CrawlResult {
        +url: str
        +success: bool
        +html: str
        +markdown: MarkdownResult
        +extracted_content: str
        +links: Dict
        +media: Dict
    }

    class OutputManager {
        +backends: List[OutputBackend]
        +save(result)
        +finalize()
    }

    class OutputBackend {
        <<abstract>>
        +save(result, meta)
        +finalize()
    }

    AsyncWebCrawler *-- BrowserConfig
    AsyncWebCrawler *-- HookRegistry
    AsyncWebCrawler *-- CrawlerRunConfig
    AdaptiveCrawler *-- AsyncWebCrawler
    CrawlerRunConfig o-- ExtractionStrategy
    CrawlerRunConfig o-- DefaultMarkdownGenerator
    CrawlerRunConfig o-- OutputBackend
    ExtractionStrategy <|-- LLMExtractionStrategy
    ExtractionStrategy <|-- JsonCssExtractionStrategy
    ContentFilterStrategy <|-- PruningContentFilter
    ContentFilterStrategy <|-- BM25ContentFilter
    DefaultMarkdownGenerator o-- ContentFilterStrategy
    OutputManager o-- OutputBackend
    AsyncWebCrawler ..> CrawlResult : produces
```

---

## 4. Deep Crawl Phase Flow

The 8 phases of `deep_crawl()` in `crawl4ai/deep_crawler.py`.

```mermaid
flowchart TD
    START([Start: deep_crawl\ncrawler, url, deep_config, run_conf])

    P1["Phase 1\nCrawl listing page\n(open session)"]
    P2{scroll=True?}
    P3["Phase 2\nscroll_to_bottom()\nmax_scrolls times"]
    P4{click_load_more?}
    P5["Phase 3\nclick_load_more()\nmax_load_more_clicks"]
    P6["Phase 4\nRe-capture HTML\nafter scrolling"]
    P7["Phase 5\nextract_links()\nfilter + deduplicate"]
    P8{paginate=True?}
    P9["Pagination loop\nclick_next_page() → extract_links()\nup to max_pages"]
    P10{use_screenshots?}
    P11["Phase 6\ntake_full_screenshot(page)"]
    P12["Close listing session"]
    P13["Phase 7\nCrawl inner pages\n(concurrent, max_inner_pages)"]
    P14{smart_filter=True?}
    P15["smart_extract()\nLLM noise filter + chunk dedup"]
    P16["Phase 8\nAggregate\nlisting + inner page content"]
    END([Return: listing_result, inner_results,\nall_content, screenshots, article_links])

    START --> P1 --> P2
    P2 -->|Yes| P3 --> P4
    P2 -->|No| P4
    P4 -->|Yes| P5 --> P6
    P4 -->|No| P6
    P6 --> P7 --> P8
    P8 -->|Yes| P9 --> P10
    P8 -->|No| P10
    P10 -->|Yes| P11 --> P12
    P10 -->|No| P12
    P12 --> P13 --> P14
    P14 -->|Yes| P15 --> P16
    P14 -->|No| P16
    P16 --> END
```

---

## 5. Pharma Intelligence Pipeline

End-to-end data flow through `PharmaPipeline.process()` in `crawl4ai/pharma_intelligence/pipeline.py`.

```mermaid
flowchart TD
    IN(["Input\nList[PharmaArticle]\n(title, text, url, source, published_at)"])

    S1["Stage 1 — Entity Extraction\nextraction.py · EntityExtractor\nMolecule, company, trial_phase,\nregulatory_body, event_type …"]
    LLM1{LLM\navailable?}
    FB1["Fallback: regex rules"]

    S2["Stage 2 — Classification\nclassifier.py · ArticleClassifier\ncategories[], primary_category, therapy_area"]
    LLM2{LLM\navailable?}
    FB2["Fallback: regex patterns"]

    S3["Stage 3 — Exclusion Filter\nfilter.py · ExclusionFilter\nshould_demote + reason"]
    SI{Strong include\nsignal?}
    HE{Hard exclude\npattern?}
    LLM3["LLM decision\n(confidence ≥ 0.65)"]

    S4["Stage 4 — Relevance Scoring\nscorer.py · RelevanceScorer\ntotal_score 0-100, breakdown, is_key_highlight"]

    S5{"Stage 5 — Scope filter / demotion\nout-of-scope? OR score < min_threshold?"}
    DEMOTE["out-of-scope → excluded=True (dropped)\nin-scope low-value → demoted=True (kept, ranked lower)"]
    KEEP["Promote as\nKey Highlight or Regular"]

    S6["Stage 6 — Deduplication\ndeduplicator.py · Deduplicator\nJaccard ≥ 0.55 OR entity fingerprint match\n→ merge to richest cluster"]

    S7["Stage 7 — Summarization\nsummarizer.py · LeadershipSummarizer\nsummary, headline, key_metric, key_points"]
    LLM7{LLM\navailable?}
    FB7["Fallback: sentence extraction"]

    S8["Stage 8 — Sort & Format\nKey Highlights first, then by score\nformatter.py → HTML email or JSON"]

    OUT(["Output\nList[PharmaIntelligenceResult]"])

    IN --> S1
    S1 --> LLM1 -->|Yes| S2
    LLM1 -->|No| FB1 --> S2
    S2 --> LLM2 -->|Yes| S3
    LLM2 -->|No| FB2 --> S3
    S3 --> SI -->|Yes, skip filter| S4
    SI -->|No| HE -->|Yes| S4
    HE -->|No| LLM3 --> S4
    S4 --> S5
    S5 -->|Yes| DEMOTE --> S6
    S5 -->|No| KEEP --> S6
    S6 --> S7
    S7 --> LLM7 -->|Yes| S8
    LLM7 -->|No| FB7 --> S8
    S8 --> OUT
```

---

## 6. Job Execution Sequence

End-to-end flow from a job creation request through to stored results, spanning the API, job engine, crawler, and pharma pipeline.

```mermaid
sequenceDiagram
    actor Client
    participant API as FastAPI (api/routers/jobs.py)
    participant DB as PostgreSQL (db.py)
    participant Engine as Job Engine (engine.py)
    participant Crawler as AsyncWebCrawler
    participant Deep as deep_crawl()
    participant Smart as smart_extract()
    participant Pharma as PharmaPipeline (optional)
    participant Outputs as OutputManager

    Client->>API: POST /api/jobs (JobCreateRequest)
    API->>DB: create_job() → status=pending
    API->>Engine: run_job_async(job_id)
    API-->>Client: 202 Accepted {job_id}

    Engine->>DB: get_job(job_id)
    Engine->>DB: update_job(status=running)

    Engine->>Crawler: AsyncWebCrawler(BrowserConfig)
    Crawler->>Crawler: _ensure_browser() — launch Chromium

    Engine->>Deep: deep_crawl(crawler, url, DeepCrawlConfig)
    Deep->>Crawler: arun(listing_url) — open session
    Crawler-->>Deep: CrawlResult (HTML)
    Deep->>Deep: scroll / load-more / pagination
    Deep->>Deep: extract_links()
    loop each article link
        Deep->>Crawler: arun(article_url)
        Crawler-->>Deep: CrawlResult (markdown)
    end
    Deep-->>Engine: {listing_result, inner_results, all_content}

    Engine->>Smart: smart_extract(all_content, strategy)
    Smart->>Smart: LLM extraction + chunk dedup + noise filter
    Smart-->>Engine: List[article dicts]

    Engine->>Engine: recency filter (is_within_last_24h, IST)

    opt summarize_with_ai=True
        Engine->>Pharma: PharmaPipeline.process(articles)
        Pharma-->>Engine: List[PharmaIntelligenceResult]
    end

    Engine->>Outputs: save(results) → JSON, CSV, PDF, Email, Blob
    Outputs-->>Engine: blob_urls, output_dir

    Engine->>DB: update_job(status=completed, article_count, blob_urls, extracted_articles)
    Engine-->>Client: (async notification / poll GET /api/jobs/{id})
```
