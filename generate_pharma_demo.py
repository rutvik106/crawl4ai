#!/usr/bin/env python3
"""
Pharma Intelligence Demo - Generate Sample CDSCO/Daily Bites Report

This script creates a realistic demonstration of the pharma intelligence pipeline
using sample articles representing CDSCO updates and global pharma news.

Run: python generate_pharma_demo.py
Output: outputs/pharma_demo_report.html + outputs/pharma_demo_report.pdf
"""

import json
import os
import tempfile
from datetime import date
from typing import Any, Dict, List

# Add project to path
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Direct imports to avoid playwright dependency (package __init__.py is temporarily renamed)
from crawl4ai.pharma_intelligence.pipeline import PharmaArticle, PharmaPipeline
from crawl4ai.pharma_intelligence.formatter import PharmaEmailFormatter
from crawl4ai.output.pdf_output import PDFReportOutput
from crawl4ai.output.base import OutputBackend

# Minimal CrawlResult for PDF output - matching the model structure
class CrawlResult:
    def __init__(self, url: str = "", success: bool = False, extracted_content: str = ""):
        self.url = url
        self.success = success
        self.extracted_content = extracted_content


# Sample CDSCO and Global Pharma News Articles
SAMPLE_ARTICLES: List[Dict[str, Any]] = [
    # Key Highlights - High relevance CDSCO approvals
    {
        "title": "CDSCO approves Zydus Lifesciences' generic heart failure drug",
        "text": "The Central Drugs Standard Control Organization (CDSCO) has approved Zydus Lifesciences' generic version of sacubitril/valsartan, a combination drug used in the treatment of heart failure. This approval marks a significant milestone for the Indian pharmaceutical market as it is the first generic approval for this molecule in India. The drug, originally marketed by Novartis as Entresto, had global sales of over $5 billion in 2024. Zydus expects to launch the product within the next 60 days.",
        "url": "https://cdsco.gov.in/approvals/2025/zydus-sacubitril-valsartan",
        "source": "CDSCO",
        "published_at": "2025-06-18",
        "category": "CDSCO Approval"
    },
    {
        "title": "Sun Pharma gets CDSCO nod for novel oncology biosimilar",
        "text": "Sun Pharmaceutical Industries has received approval from CDSCO for its trastuzumab biosimilar, indicated for HER2-positive breast cancer. The approval is based on comprehensive analytical, preclinical, and clinical data including a Phase III equivalence study. This is Sun Pharma's third oncology biosimilar approval in the past 18 months. The company has invested over ₹200 crore in developing the manufacturing facility in Gujarat.",
        "url": "https://sunpharma.com/media/cdsco-trastuzumab-approval",
        "source": "Sun Pharma",
        "published_at": "2025-06-17",
        "category": "CDSCO Approval"
    },
    {
        "title": "Torrent Pharma acquires German specialty pharma company for €450M",
        "text": "Torrent Pharmaceuticals has announced the acquisition of Berlin-based specialty pharmaceutical company Heumann Pharma for €450 million. The acquisition gives Torrent access to Heumann's portfolio of 85 registered products across cardiovascular, CNS, and pain therapeutic areas in Germany and Eastern European markets. The transaction is expected to close in Q3 2025, subject to regulatory approvals. Heumann reported revenues of €180 million in 2024 with EBITDA margins of 28%.",
        "url": "https://torrentpharma.com/investors/acquisitions/heumann-2025",
        "source": "Business Wire",
        "published_at": "2025-06-16",
        "category": "M&A Activity"
    },
    {
        "title": "FDA approves AstraZeneca's rare disease gene therapy",
        "text": "The U.S. Food and Drug Administration has approved AstraZeneca's gene therapy for the treatment of metachromatic leukodystrophy (MLD), a rare and fatal inherited neurological disorder. The therapy, priced at $2.8 million per treatment, is the second gene therapy approved for MLD globally. The approval was based on data from 31 patients showing sustained clinical benefit at 3-year follow-up. AstraZeneca plans to seek EMA and CDSCO approvals in the next 6 months.",
        "url": "https://fda.gov/news-events/press-announcements/fda-approves-mld-gene-therapy",
        "source": "FDA",
        "published_at": "2025-06-15",
        "category": "FDA Approval"
    },
    {
        "title": "Lupin gets orphan drug designation for pediatric rare disease candidate",
        "text": "Lupin Limited has announced that its novel small molecule candidate for the treatment of Duchenne muscular dystrophy has received orphan drug designation from the FDA. The designation provides Lupin with 7 years of market exclusivity upon approval and waiver of FDA application fees. The candidate is currently in Phase II clinical trials with 48 patients enrolled across 12 sites in the US. Top-line results are expected in Q1 2026.",
        "url": "https://lupin.com/media/fda-orphan-drug-designation-2025",
        "source": "Lupin",
        "published_at": "2025-06-14",
        "category": "Orphan Drug Designation"
    },

    # Other News - Lower relevance items
    {
        "title": "Dr. Reddy's launches generic cardiovascular drug in US market",
        "text": "Dr. Reddy's Laboratories has launched its generic version of amlodipine/atorvastatin combination tablets in the US market. The product is the generic equivalent of Pfizer's Caduet. The company has received approval from USFDA for the abbreviated new drug application. The product was launched immediately following approval.",
        "url": "https://drreddys.com/news/us-launch-caduet-generic",
        "source": "Dr. Reddy's",
        "published_at": "2025-06-18",
        "category": "ANDA Approval"
    },
    {
        "title": "Cipla expands manufacturing capacity for respiratory products",
        "text": "Cipla has announced the expansion of its manufacturing facility in Indore with an investment of ₹150 crore. The expansion will increase the company's capacity for metered-dose inhalers by 40%. The facility is expected to be operational by Q4 2025.",
        "url": "https://cipla.com/media/indore-expansion-2025",
        "source": "Cipla",
        "published_at": "2025-06-17",
        "category": "Manufacturing"
    },
    {
        "title": "Glenmark gets USFDA approval for dermatology product",
        "text": "Glenmark Pharmaceuticals has received approval from the USFDA for its topical cream for the treatment of inflammatory skin conditions. The product is the generic equivalent of a branded product with annual US sales of approximately $120 million. Glenmark plans to launch the product in the next quarter.",
        "url": "https://glenmarkpharma.com/usfda-dermatology-approval",
        "source": "Glenmark",
        "published_at": "2025-06-16",
        "category": "ANDA Approval"
    },
    {
        "title": "Biocon Biologics reports Phase III data for insulin biosimilar",
        "text": "Biocon Biologics has presented positive Phase III data for its insulin glargine biosimilar at the American Diabetes Association conference. The study met its primary endpoint demonstrating bioequivalence to the reference product. The company plans to file for regulatory approval in Europe and India in H2 2025.",
        "url": "https://biocon.com/clinical-trials/insulin-glargine-phase3",
        "source": "Biocon",
        "published_at": "2025-06-15",
        "category": "Clinical Trial"
    },
    {
        "title": "Strides Pharma secures licensing deal for emerging markets",
        "text": "Strides Pharma Science has entered into a licensing agreement with a European pharma company for the commercialization of 12 oral solid dosage products in Africa and Southeast Asian markets. The deal includes upfront payments of $8 million plus double-digit royalties on net sales.",
        "url": "https://strides.com/licensing-emerging-markets-2025",
        "source": "Strides",
        "published_at": "2025-06-14",
        "category": "Licensing Deal"
    },
    {
        "title": "Alembic Pharmaceuticals receives EMA approval for oncology product",
        "text": "Alembic Pharmaceuticals has received marketing authorization from the European Medicines Agency for its generic oncology product used in the treatment of multiple myeloma. This is Alembic's second EMA approval for an oncology product in 2025.",
        "url": "https://alembicpharmaceuticals.com/ema-oncology-approval",
        "source": "Alembic",
        "published_at": "2025-06-13",
        "category": "EMA Approval"
    },
    {
        "title": "Wockhardt initiates Phase I study for novel antibiotic",
        "text": "Wockhardt has announced the initiation of a Phase I clinical study for its novel antibiotic candidate targeting multi-drug resistant bacterial infections. The study will enroll 60 healthy volunteers across sites in the UK.",
        "url": "https://wockhardt.com/research/phase1-antibiotic",
        "source": "Wockhardt",
        "published_at": "2025-06-12",
        "category": "Clinical Trial"
    },
]


def run_demo():
    """Run the pharma intelligence pipeline demo."""
    print("=" * 70)
    print("PHARMA INTELLIGENCE PIPELINE DEMO")
    print("Daily Bites & CDSCO Updates Curation")
    print("=" * 70)
    print()

    # Create articles
    articles = [
        PharmaArticle(
            title=a["title"],
            text=a["text"],
            url=a["url"],
            source=a["source"],
            published_at=a["published_at"],
            category=a["category"],
        )
        for a in SAMPLE_ARTICLES
    ]

    print(f"Processing {len(articles)} sample articles...")
    print()

    # Initialize pipeline (without LLM for demo - uses rule-based fallbacks)
    pipeline = PharmaPipeline(
        llm_client=None,  # Rule-based extraction for demo
        min_score_threshold=10,
        run_deduplication=True,
    )

    # Process articles
    results = pipeline.process(articles)

    # Summary statistics (never-drop policy: nothing is excluded; low-value items
    # are demoted to Other News, and only de-duplication reduces the item count)
    highlights = [r for r in results if r.is_key_highlight]
    other = [r for r in results if not r.is_key_highlight]
    demoted = sum(1 for r in results if r.demoted)
    consolidated = len(SAMPLE_ARTICLES) - len(results)

    print("PROCESSING RESULTS:")
    print("-" * 50)
    print(f"Total Articles:          {len(SAMPLE_ARTICLES)}")
    print(f"Retained (never-drop):   {len(results)}")
    print(f"Key Highlights:          {len(highlights)}")
    print(f"Other News:              {len(other)}")
    print(f"Demoted to Other News:   {demoted}")
    print(f"Consolidated (dedup):    {consolidated}")
    print()

    # Show top highlights
    print("KEY HIGHLIGHTS:")
    print("-" * 50)
    for item in highlights[:5]:
        score = item.relevance_score
        molecule = item.entities.get('molecule', 'N/A')
        company = item.entities.get('company', 'N/A')
        print(f"  [{score:2d}] {item.headline[:60]}...")
        print(f"       Molecule: {molecule} | Company: {company}")
        print()

    # Generate outputs
    output_dir = os.path.join(os.path.dirname(__file__), "outputs")
    os.makedirs(output_dir, exist_ok=True)

    # 1. Generate HTML Email Report
    formatter = PharmaEmailFormatter()
    all_items = [r.to_dict() for r in results]
    html_report = formatter.format_report(
        items=all_items,
        report_date=date.today(),
        title="Daily Pharma Intelligence Brief"
    )

    html_path = os.path.join(output_dir, "pharma_demo_report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_report)
    print(f"HTML Report saved: {html_path}")

    # 2. Generate PDF Report
    pdf_path = os.path.join(output_dir, "pharma_demo_report.pdf")

    # Convert to format compatible with PDF output
    pdf_articles = []
    for r in results:
        pdf_articles.append({
            "title": r.headline or r.title,
            "source": r.source or "Multiple Sources" if r.is_consolidated else r.source,
            "category": r.primary_category or "Pharma News",
            "summary": r.summary,
            "time_ago": r.published_at,
            "relevance_score": r.relevance_score,
            "molecule": r.entities.get("molecule"),
            "company": r.entities.get("company"),
            "therapy_area": r.therapy_area,
        })

    # Create PDF
    project_root = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(project_root, "New-Logo-Impeerical.jpg")

    backend = PDFReportOutput(
        path=pdf_path,
        title="Daily Pharma Intelligence Brief - CDSCO Updates",
        logo_path=logo_path if os.path.exists(logo_path) else None,
        ai_summary=f"This report covers {len(results)} curated pharma intelligence items including {len(highlights)} key highlights. Major events include CDSCO approvals for Zydus and Sun Pharma, a significant M&A transaction by Torrent Pharma, and FDA approvals in rare disease gene therapy.",
    )

    result = CrawlResult(
        url="https://cdsco.gov.in + pharma-sources",
        success=True,
        extracted_content=json.dumps(pdf_articles),
    )
    backend.save(result)
    backend.finalize()

    print(f"PDF Report saved:  {pdf_path}")
    print()

    # 3. Save JSON data for review
    json_summary = formatter.format_json_summary(all_items)
    json_summary["generated_at"] = date.today().isoformat()
    json_summary["demoted_count"] = demoted
    json_summary["consolidated_count"] = consolidated
    json_summary["excluded_count"] = 0  # never-drop policy; retained for compatibility
    json_summary["pipeline_version"] = "v1.1.0"

    json_path = os.path.join(output_dir, "pharma_demo_data.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_summary, f, indent=2, ensure_ascii=False)
    print(f"JSON Data saved:   {json_path}")

    print()
    print("=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print()
    print("Deliverables generated:")
    print(f"  1. {html_path}")
    print(f"  2. {pdf_path}")
    print(f"  3. {json_path}")
    print()
    print("These files can be shared with stakeholders for review.")

    return html_path, pdf_path, json_path


if __name__ == "__main__":
    run_demo()
