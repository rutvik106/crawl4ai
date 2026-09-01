# AI-Powered Pharma Intelligence Platform

### Revised Commercial Proposal — Deployment Options & Cost Structure

**Prepared for:** Torrent Pharmaceuticals Ltd. (TPL)
**Prepared by:** [Your Name / Company]
**Date:** August 2026
**Validity:** 30 days from date of issue

---

## 1. Purpose of This Document

Following our discussion, this revised proposal:

1. Explains every cost component in **simple, non-technical language**
2. Clearly **separates** one-time costs, recurring third-party costs, technical services, and annual maintenance — with no overlap
3. Presents **three deployment options**, showing exactly **who pays for what** under each, with advantages and limitations
4. Lists all backend services, AI models, and infrastructure the platform depends on, for review by TPL's IT and procurement teams

---

## 2. What the Platform Does (In Plain Terms)

Every day, the platform automatically:

1. **Visits** the news and regulatory websites you choose
2. **Reads** every new article using AI, and filters out irrelevant content
3. **Identifies** what matters — competitor moves, regulatory milestones, key developments
4. **Compiles** everything into your Daily Bites report format
5. **Delivers** the report to your team by email, on schedule, with a link to every original source

Your team receives ready-to-read intelligence without anyone manually scanning websites.

---

## 3. The Four Cost Components (No Overlap)

Think of the costs in four clearly separate buckets:

| # | Component | What it pays for | Nature |
|---|---|---|---|
| A | **License & Implementation** | The software itself, set up and ready to use | One-time |
| B | **Third-Party Running Costs** | Bills from outside vendors: AI usage, cloud hosting, proxy services | Monthly, usage-based |
| C | **Managed Technical Services** | Our people watching the system daily: checking reports went out, fixing failed or delayed jobs, monitoring output quality | Monthly |
| D | **Annual Maintenance (AMC)** | Keeping the software healthy over time: upgrades when AI models or technologies change, fixing sources when websites redesign, priority support | Yearly |

**The difference between C and D, simply:**
- **C (monthly)** = day-to-day operations — "did today's report go out correctly?"
- **D (yearly)** = long-term upkeep — "the AI model we use was upgraded by its provider; we updated the platform so nothing breaks." Technology platforms need this continuously because the AI ecosystem changes every few months.

### Component A — License & Implementation: ₹12,00,000 (one-time, same in all options)

- Full platform license for TPL (single organization)
- Deployment on chosen infrastructure
- Onboarding of your target websites and sources
- Report format built to your specification
- Team training and handover

### Component B — Third-Party Running Costs (usage-based)

These are real bills from outside vendors. They vary with the number of websites monitored and how often they are checked:

| Service | Vendor (current) | Purpose | Indicative monthly cost* |
|---|---|---|---|
| AI language models | Anthropic (Claude), Groq, other inference providers | Reading, analyzing, scoring, and summarizing articles | ₹35,000 – ₹70,000 |
| Cloud hosting & database | Railway.com (PostgreSQL included) | Running the platform 24×7 | ₹10,000 – ₹15,000 |
| Proxy / website access | BrightData | Accessing websites that block automated visitors | ₹8,000 – ₹15,000 |
| File storage & email delivery | Vercel Blob, email service | Storing reports and delivering emails | ₹3,000 – ₹6,000 |

*At medium usage (current source list, daily crawls). Heavy usage — e.g., 100+ scheduled jobs per day or a large expansion of sources — increases these costs. Additional websites can generally be added at no fixed per-website charge as long as overall volume stays within the agreed usage level.*

### Component C — Managed Technical Services: ₹50,000 / month

Daily human oversight by our technical team:
- Monitoring every scheduled job and report delivery
- Investigating and resolving failed or delayed jobs
- Watching output quality and correcting drift
- Remote support during business hours

### Component D — Annual Maintenance Contract (AMC): ₹2,40,000 / year

- Software upgrades when underlying AI models, libraries, or services change (e.g., an AI provider retires an old model — we migrate the platform to the new one)
- Fixing sources when websites redesign their layouts
- Security patches and compatibility updates
- Priority support; on-site visits arranged when required (travel at actuals)

---

## 4. Three Deployment Options

### Option 1 — Hosted by Us (Fully Managed)

Everything runs on our infrastructure. TPL simply receives the reports and uses the dashboard.

| Component | Amount | Paid by TPL to |
|---|---|---|
| A. License & implementation (one-time) | ₹12,00,000 | Us |
| B + C. All-inclusive monthly (third-party costs + daily technical services, bundled) | ₹1,00,000 – ₹1,50,000 / month | Us |
| D. AMC | ₹2,40,000 / year | Us |

**Advantages:** Fastest to start (already running); zero burden on TPL IT; one consolidated bill; we absorb minor usage fluctuations.
**Limitations:** Data resides on our cloud infrastructure; third-party subscriptions in our name.

### Option 2 — Deployed on TPL's Server / Cloud

The platform is installed on TPL's existing server or cloud environment. TPL purchases the third-party subscriptions directly through its own procurement.

| Component | Amount | Paid by TPL to |
|---|---|---|
| A. License & implementation (one-time) | ₹12,00,000 | Us |
| B. Third-party subscriptions (AI, proxy, etc.) | ~₹45,000 – ₹90,000 / month (actuals) | Vendors directly |
| C. Managed technical services | ₹50,000 / month | Us |
| D. AMC | ₹2,40,000 / year | Us |

**Advantages:** Data stays within TPL's environment; full visibility and ownership of subscription costs; subscriptions under TPL's own accounts.
**Limitations:** Requires TPL IT approval and server access for our team; subject to TPL's IT policies (which may restrict installation on the corporate server); TPL manages vendor procurement.

### Option 3 — Standalone Setup Within TPL Premises

A dedicated machine (or separate cloud environment) operating independently of TPL's main corporate server — with its own internet connection and isolated services. Practical if IT policy restricts installation on the corporate server.

| Component | Amount | Paid by TPL to |
|---|---|---|
| A. License & implementation (one-time) | ₹12,00,000 | Us |
| Hardware (one-time, via TPL purchase team) | ~₹1,50,000 – ₹2,50,000 | Hardware vendor |
| B. Third-party subscriptions (AI, proxy, etc.) | ~₹40,000 – ₹80,000 / month (actuals) | Vendors directly |
| C. Managed technical services | ₹50,000 / month | Us |
| D. AMC | ₹2,40,000 / year | Us |

**Recommended hardware specification (no GPU required — AI runs via cloud APIs):**
- 8-core CPU, 32 GB RAM, 500 GB SSD
- Ubuntu Linux server OS
- Dedicated broadband connection
- Optional: GPU (24 GB+ VRAM) only if TPL later prefers fully on-premise AI models instead of cloud AI APIs — this would raise hardware cost but reduce monthly AI subscription costs

**Advantages:** Physically within TPL premises; isolated from the corporate network; independent internet and licensing; clear ownership of every component.
**Limitations:** Hardware procurement lead time; TPL bears hardware upkeep; our support is remote-first with on-site visits as needed (travel at actuals).

### Side-by-Side Summary

| | Option 1: We host | Option 2: TPL server | Option 3: Standalone at TPL |
|---|---|---|---|
| One-time (license) | ₹12,00,000 | ₹12,00,000 | ₹12,00,000 + hardware |
| Monthly to us | ₹1,00,000 – ₹1,50,000 | ₹50,000 | ₹50,000 |
| Monthly to vendors | — (included) | ~₹45,000 – ₹90,000 | ~₹40,000 – ₹80,000 |
| AMC (yearly, to us) | ₹2,40,000 | ₹2,40,000 | ₹2,40,000 |
| Data location | Our cloud | TPL environment | TPL premises |
| TPL IT involvement | None | High | Medium |
| Time to start | Immediate | After IT approval | After procurement |

---

## 5. Complete List of Platform Dependencies (For IT & Procurement Review)

| Category | Service / Technology | Required? | Cost bearer (Options 2 & 3) |
|---|---|---|---|
| AI models | Anthropic Claude (Sonnet / Opus) — analysis & extraction | Yes | TPL subscription |
| AI models | Groq (or similar fast inference) — summarization & filtering | Yes | TPL subscription |
| Hosting | Railway.com, or TPL server/cloud | Yes | TPL (own infra) |
| Database | PostgreSQL | Yes | Included with hosting |
| Website access | BrightData proxy (for protected websites) | Yes | TPL subscription |
| Storage | Vercel Blob or local disk storage | Yes | TPL (local = free) |
| Email | SMTP / email delivery service | Yes | TPL (can use existing) |
| Browser engine | Playwright + Chromium (open-source) | Yes | Free |
| Runtime | Python 3 + open-source libraries | Yes | Free |

Our technical team is available to meet TPL's IT team to walk through security, access, and deployment requirements for whichever option is preferred.

---

## 6. Changes & Enhancements — How Future Work Is Priced

We understand a flat day-rate is hard to evaluate, so pricing works as follows:

1. **Included at no charge (under AMC):** bug fixes, source repairs after website redesigns, compatibility upgrades, minor report tweaks (e.g., wording, small layout adjustments)
2. **Adding websites to existing monitoring:** generally included, within the agreed usage level
3. **New features and larger changes:** priced **per job** — we scope the request, share a written estimate with effort and a fixed price, and begin only after your approval. Larger enhancements are documented through a signed addendum.

**Illustrative examples (indicative only):**

| Example request | Indicative price |
|---|---|
| New report format or additional report type | ₹35,000 – ₹70,000 |
| New category of intelligence (e.g., new milestone type with custom logic) | ₹50,000 – ₹1,00,000 |
| New source *type* requiring different handling (e.g., a portal behind login) | ₹40,000 – ₹80,000 |
| Major new module or workflow | Scoped individually via addendum |

No work is ever billed without a written, pre-approved estimate.

---

## 7. Ongoing Refinement — Setting the Right Expectation

The platform is live and delivering today, but tuning the output to fully meet TPL's expectations is an ongoing, collaborative process. We estimate **3–4 further months** of active refinement:

| Phase | Focus |
|---|---|
| Months 1–2 | Output accuracy tuning against your team's feedback; report format refinement; source list finalization |
| Months 2–3 | Extraction accuracy hardening; duplicate story handling; scoring calibration |
| Months 3–4 | Enterprise readiness — security hardening, audit logs, deployment migration (if Option 2 or 3 selected) |

After this period, the platform runs in steady state under Components B, C, and D.

---

## 8. Terms

1. All prices exclusive of GST; quoted in INR.
2. License covers a single deployment for one organization; not transferable.
3. Third-party costs under Options 2 and 3 are billed by vendors at actuals to TPL; indicative ranges shown are estimates at medium usage.
4. All data, reports, and outputs remain TPL's property.
5. Payment terms: license 50% on signing, 50% on go-live; monthly and AMC billed in advance.
6. Either party may terminate recurring services with 60 days' written notice.
7. On-site visit travel and stay, where required, billed at actuals.

---

## 9. Next Steps

1. TPL IT & procurement review Sections 4 and 5
2. Joint call between our technical team and TPL IT to resolve deployment questions
3. Management selects preferred deployment option
4. Commercial sign-off and (if applicable) subscription procurement begins

---

*[Your Name / Company] · [Email] · [Phone]*
