"""Tests for PDF report output backend."""

import json
import os
import tempfile

import pytest

from crawl4ai.output.pdf_output import PDFReportOutput
from crawl4ai.models import CrawlResult


@pytest.fixture
def sample_articles():
    return [
        {
            "title": "Pharma Giant Acquires Biotech Startup for $2B",
            "source": "Reuters",
            "category": "M&A",
            "summary": "Major pharmaceutical company announces acquisition of promising biotech firm.",
            "time_ago": "2 hours ago",
        },
        {
            "title": "FDA Approves New Cancer Treatment Drug",
            "source": "Medical News Today",
            "category": "Drug Approvals",
            "summary": "The FDA has granted approval for a breakthrough immunotherapy drug for lung cancer.",
            "time_ago": "4 hours ago",
        },
        {
            "title": "Healthcare Stocks Rally After Earnings Reports",
            "source": "Bloomberg",
            "category": "Markets",
            "summary": "Healthcare sector sees broad gains as major companies beat earnings expectations.",
            "time_ago": "1 hour ago",
        },
    ]


def test_pdf_generates_file(sample_articles):
    """PDF backend should produce a valid PDF file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "report.pdf")
        backend = PDFReportOutput(path=pdf_path, title="Test News Digest")

        result = CrawlResult(
            url="https://example.com/news",
            success=True,
            extracted_content=json.dumps(sample_articles),
        )
        backend.save(result)
        backend.finalize()

        assert os.path.exists(pdf_path)
        size = os.path.getsize(pdf_path)
        assert size > 1000, f"PDF too small ({size} bytes), likely empty"

        # Check it starts with PDF magic bytes
        with open(pdf_path, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-", f"Not a valid PDF: {header}"


def test_pdf_with_ai_summary(sample_articles):
    """PDF should render the AI summary section when provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "report.pdf")
        backend = PDFReportOutput(
            path=pdf_path,
            title="Test Digest",
            ai_summary="Today's pharma news is dominated by M&A activity and FDA approvals.",
        )

        result = CrawlResult(
            url="https://example.com/news",
            success=True,
            extracted_content=json.dumps(sample_articles),
        )
        backend.save(result)
        backend.finalize()

        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 1000


def test_pdf_empty_articles():
    """PDF should handle empty article list gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "report.pdf")
        backend = PDFReportOutput(path=pdf_path, title="Empty Report")

        result = CrawlResult(
            url="https://example.com",
            success=True,
            extracted_content="[]",
        )
        backend.save(result)
        backend.finalize()

        assert os.path.exists(pdf_path)
        with open(pdf_path, "rb") as f:
            assert f.read(5) == b"%PDF-"


def test_pdf_with_logo(sample_articles):
    """PDF should not crash when logo path is provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "report.pdf")
        # Use the project logo if it exists
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        logo = os.path.join(project_root, "New-Logo-Impeerical.jpg")

        backend = PDFReportOutput(
            path=pdf_path,
            title="Logo Report",
            logo_path=logo if os.path.exists(logo) else None,
        )

        result = CrawlResult(
            url="https://example.com/news",
            success=True,
            extracted_content=json.dumps(sample_articles),
        )
        backend.save(result)
        backend.finalize()

        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 1000


def test_pdf_many_articles():
    """PDF should handle many articles spanning multiple pages."""
    articles = [
        {
            "title": f"Article {i}: Detailed pharmaceutical industry news headline with some length",
            "source": f"Source {i}",
            "category": "Pharma",
            "summary": f"This is a detailed summary of article {i} covering important industry developments and regulatory changes.",
            "time_ago": f"{i} hours ago",
        }
        for i in range(1, 30)
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "report.pdf")
        backend = PDFReportOutput(path=pdf_path, title="Large Report")

        result = CrawlResult(
            url="https://example.com/news",
            success=True,
            extracted_content=json.dumps(articles),
        )
        backend.save(result)
        backend.finalize()

        assert os.path.exists(pdf_path)
        # Multi-page PDF should be larger
        assert os.path.getsize(pdf_path) > 5000


def test_pdf_unicode_handling():
    """PDF should handle special characters gracefully."""
    articles = [
        {
            "title": "Drug Price \u2014 Analysis & Forecast (Q1\u20132026)",
            "source": "M\u00e9dical Fran\u00e7ais",
            "summary": "Special chars: \u00a3100M deal, 50\u00b0C storage, \u00b110% margin",
        },
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "report.pdf")
        backend = PDFReportOutput(path=pdf_path, title="Unicode Test")

        result = CrawlResult(
            url="https://example.com",
            success=True,
            extracted_content=json.dumps(articles),
        )
        backend.save(result)
        backend.finalize()

        assert os.path.exists(pdf_path)
        with open(pdf_path, "rb") as f:
            assert f.read(5) == b"%PDF-"
