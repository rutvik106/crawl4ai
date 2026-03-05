# Crawl4AI — Feature Overview

> **AI-powered web crawling & data extraction platform** — built for modern intelligence workflows.

---

## Why Crawl4AI?

Crawl4AI turns any website into clean, structured data — automatically. It combines a production-grade web crawler, LLM-powered extraction, smart content filtering, automated scheduling, and multi-channel delivery into one unified platform. Whether you're monitoring competitors, aggregating news, or building AI pipelines, Crawl4AI does the heavy lifting.

---

## Core Features

### Web Crawling Engine

- **Async, headless browser crawling** powered by Playwright (Chromium) — handles JavaScript-heavy, dynamic pages out of the box
- **JavaScript execution** — run custom JS on any page before extraction
- **Session management** — maintain browser state across multi-step crawls
- **Stealth mode** — advanced anti-bot fingerprint masking (user agent rotation, navigator spoofing, plugin arrays, automation indicator hiding)
- **Configurable concurrency** — parallel crawling with memory-adaptive dispatching across hundreds of URLs simultaneously
- **Smart request control** — custom headers, proxy support, cookie management, request blocking by URL pattern

### Deep Crawling

- **Automatic pagination** — follows "Next Page" links and numbered paginator patterns
- **"Load More" button handling** — clicks and expands dynamically loaded content
- **Auto-scroll** — scrolls pages to trigger lazy-loaded content before extraction
- **Inner page following** — recursively crawls linked pages with configurable depth
- **Adaptive stopping** — automatically determines when enough content has been collected using confidence scoring

### Data Extraction

- **HTML → Markdown conversion** — clean, LLM-ready output with configurable content filters
- **CSS & XPath extraction** — precise, schema-driven structured JSON output
- **LLM-based extraction** — natural-language instructions to extract any data shape from any page
- **Auto schema generation** — LLM generates CSS extraction schemas from sample HTML automatically
- **Multi-provider LLM support** — OpenAI, Groq, Ollama, and any provider via LiteLLM
- **Multi-strategy fallback pipeline** — deterministic selectors → heuristic parsers → LLM fallback
- **Media & link extraction** — pulls all images, files, and links with full metadata

### Content Intelligence

- **AI-powered noise removal** — eliminates boilerplate, ads, navigation menus, and low-quality content
- **Configurable content filters** — word-count thresholds, tag/selector pruning, custom rules
- **Raw and cleaned HTML access** — full control over what gets processed
- **LLM summarization** — per-article summaries and consolidated weekly/monthly digest reports
- **AI-generated digest reports** — automatic summaries across all crawled content for a time period

---

## Scheduling & Automation

- **Cron-based scheduling** — any schedule expression (hourly, daily, weekly, custom)
- **Job lifecycle management** — create, run, pause, rerun, and delete crawl jobs
- **Background execution** — jobs run as background workers with full status tracking
- **Job history & audit trail** — timestamps, error logs, and result metadata for every run
- **Idempotent reruns** — safely re-execute any past job with the same configuration

---

## Multi-Channel Delivery

| Channel | Details |
|---------|---------|
| **Email** | SMTP & SendGrid support; configurable recipient lists per schedule |
| **Webhook** | HTTP callback notifications on job completion |
| **JSON file** | Export results as structured JSON |
| **CSV file** | Tabular export for spreadsheet workflows |
| **SQLite** | Local database storage for programmatic access |
| **HTML report** | Formatted HTML reports for human review |

---

## REST API

A full-featured FastAPI service exposes everything over HTTP:

- **Jobs API** — create, list, retrieve, rerun, delete crawl jobs
- **Results API** — fetch extracted data from any completed job
- **Schedules API** — full CRUD for recurring schedule management
- **Reports API** — on-demand and automated AI digest report generation
- **Users API** — user creation and management (admin)
- **Settings API** — configure LLM provider, SMTP, and system defaults
- **Statistics API** — system-level metrics and usage data
- **Authentication** — JWT-based login and token auth
- **CORS support** — ready for frontend and cross-origin integration

---

## Web Dashboard

A full web application (Next.js) for managing the entire platform without writing code:

- **Job creation wizard** — step-by-step UI to configure URL, extraction schema, recipients, and options
- **Job list & history** — view all past and upcoming runs with status indicators
- **Job detail view** — inspect extracted results, logs, and metadata for any run
- **Schedule management** — create and manage recurring crawls with cron expressions
- **Consolidated report UI** — configure weekly/monthly AI digests per schedule
- **Settings panel** — manage LLM provider keys, SMTP credentials, and system defaults
- **User management** — admin interface for creating and managing platform users
- **Role-based access control** — super admin, admin, and standard user roles
- **Authentication** — secure login with session management

---

## Developer Experience

- **Python library** — use `AsyncWebCrawler` directly in any Python project
- **Lifecycle hooks** — plug in custom async code at any stage: browser creation, page load, JS execution, HTML capture, error handling
- **Streaming results** — stream results as they complete for real-time pipelines
- **Configurable output formats** — raw HTML, cleaned HTML, full Markdown, fit Markdown, links list
- **Batch crawling** — `arun_many()` for parallel multi-URL execution with adaptive memory management
- **Docker support** — `Dockerfile` and `Procfile` included for containerized deployment
- **Test suite** — pytest + pytest-asyncio coverage for crawler, extraction, markdown, hooks, and configuration

---

## Authentication & Security

- **Cookie and local storage control** — set browser state for authenticated crawls
- **Login automation** — define multi-step login flows (fill, click, wait, JS) with success indicators
- **Custom request headers** — set any HTTP header on outbound requests
- **Proxy routing** — route crawl traffic through HTTP proxies

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Browser automation | Playwright (Chromium) |
| HTML parsing | BeautifulSoup4 |
| Markdown conversion | html2text |
| REST API | FastAPI |
| Web frontend | Next.js (TypeScript) |
| Job scheduling | APScheduler |
| Database | SQLite |
| LLM abstraction | LiteLLM |
| Data validation | Pydantic |
| Language | Python 3.9+ |

---

## Use Case Highlights

- **News & media monitoring** — aggregate, filter, and summarize news from any source on a schedule
- **Competitor intelligence** — track product pages, pricing, and announcements automatically
- **Research automation** — extract structured data from academic, government, or industry sites
- **Content pipelines** — feed clean web content into RAG, vector databases, or LLM workflows
- **Regulatory & compliance tracking** — monitor policy pages and regulatory sites for changes
- **Lead generation** — extract contact and company data from directories and listing sites
- **E-commerce monitoring** — track product listings, availability, and pricing at scale

---

*Built on open-source foundations. Designed for production.*
