"""Test output backends."""

import csv
import json
import os
import tempfile

from crawl4ai import (
    CrawlResult,
    MarkdownResult,
    JsonFileOutput,
    CsvFileOutput,
    SQLiteOutput,
    HTMLReportOutput,
    OutputManager,
)


def _make_result(url="https://example.com", md="# Test\n\nHello world", extracted=None):
    return CrawlResult(
        url=url,
        success=True,
        status_code=200,
        html="<h1>Test</h1>",
        markdown=MarkdownResult(raw_markdown=md, fit_markdown=""),
        extracted_content=extracted,
    )


class TestJsonFileOutput:
    def test_save_and_read(self, tmp_path):
        path = str(tmp_path / "out.json")
        backend = JsonFileOutput(path=path, append=False)
        backend.save(_make_result())
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["url"] == "https://example.com"
        assert data[0]["success"] is True

    def test_append_mode(self, tmp_path):
        path = str(tmp_path / "out.json")
        backend = JsonFileOutput(path=path, append=False)
        backend.save(_make_result(url="https://a.com"))
        backend.save(_make_result(url="https://b.com"))
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 2

    def test_with_extracted_content(self, tmp_path):
        path = str(tmp_path / "out.json")
        backend = JsonFileOutput(path=path, append=False)
        backend.save(_make_result(extracted='[{"title": "Test"}]'))
        with open(path) as f:
            data = json.load(f)
        assert data[0]["extracted"] == [{"title": "Test"}]


class TestCsvFileOutput:
    def test_save_and_read(self, tmp_path):
        path = str(tmp_path / "out.csv")
        backend = CsvFileOutput(path=path)
        backend.save(_make_result())
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["url"] == "https://example.com"

    def test_multiple_rows(self, tmp_path):
        path = str(tmp_path / "out.csv")
        backend = CsvFileOutput(path=path)
        backend.save(_make_result(url="https://a.com"))
        backend.save(_make_result(url="https://b.com"))
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2


class TestSQLiteOutput:
    def test_save_and_query(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        db = SQLiteOutput(db_path=db_path)
        db.save(_make_result())
        rows = db.query("SELECT * FROM crawl_results")
        assert len(rows) == 1
        assert rows[0]["url"] == "https://example.com"
        db.finalize()

    def test_latest(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        db = SQLiteOutput(db_path=db_path)
        db.save(_make_result(url="https://a.com"))
        db.save(_make_result(url="https://b.com"))
        db.save(_make_result(url="https://c.com"))
        latest = db.latest(2)
        assert len(latest) == 2
        assert latest[0]["url"] == "https://c.com"
        db.finalize()

    def test_stats(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        db = SQLiteOutput(db_path=db_path)
        db.save(_make_result())
        db.save(CrawlResult(
            url="https://fail.com", success=False,
            markdown=MarkdownResult(), error_message="timeout"
        ))
        stats = db.stats()
        assert stats["total"] == 2
        assert stats["successes"] == 1
        assert stats["failures"] == 1
        db.finalize()


class TestHTMLReportOutput:
    def test_generates_html_file(self, tmp_path):
        path = str(tmp_path / "report.html")
        backend = HTMLReportOutput(path=path, title="Test Report")
        backend.save(_make_result())
        backend.save(_make_result(url="https://other.com"))
        backend.finalize()
        assert os.path.exists(path)
        with open(path) as f:
            html = f.read()
        assert "Test Report" in html
        assert "example.com" in html
        assert "other.com" in html


class TestOutputManager:
    def test_dispatches_to_multiple_backends(self, tmp_path):
        json_path = str(tmp_path / "out.json")
        csv_path = str(tmp_path / "out.csv")
        manager = OutputManager([
            JsonFileOutput(path=json_path, append=False),
            CsvFileOutput(path=csv_path),
        ])
        manager.save(_make_result())
        manager.finalize()

        with open(json_path) as f:
            assert len(json.load(f)) == 1
        with open(csv_path) as f:
            assert len(list(csv.DictReader(f))) == 1

    def test_save_many(self, tmp_path):
        json_path = str(tmp_path / "out.json")
        manager = OutputManager([JsonFileOutput(path=json_path, append=False)])
        manager.save_many([_make_result(url="https://a.com"), _make_result(url="https://b.com")])
        with open(json_path) as f:
            assert len(json.load(f)) == 2
