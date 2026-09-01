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


# ── EmailOutput transport selection ──
#
# Regression guard for the outage where the hardcoded HTTP email API started
# returning "HTTP 401 Invalid or expired token". Every digest and pharma brief
# was blocked because that endpoint was the only transport and needs a bearer
# token callers cannot supply. SMTP is now primary; the API is a fallback.

SMTP_CREDS = {
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "smtp_user": "sender@example.com",
    "smtp_password": "secret",
}


class TestEmailOutputTransport:
    def _result(self):
        return _make_result(extracted=json.dumps([{"title": "A Real Headline Here"}]))

    def test_smtp_used_when_configured(self):
        from crawl4ai.output.email_output import EmailOutput

        out = EmailOutput(to="a@b.com", **SMTP_CREDS)
        assert out.smtp_configured
        sent, api_calls = [], []
        out._send_via_smtp = lambda r, h: sent.append(r)
        out._send_via_api = lambda r, h: api_calls.append(r)

        out.save(self._result())
        out.finalize()

        assert sent == ["a@b.com"]
        assert api_calls == [], "SMTP succeeded, so the HTTP API must not be called"

    def test_falls_back_to_api_when_smtp_not_configured(self):
        from crawl4ai.output.email_output import EmailOutput

        out = EmailOutput(to="a@b.com")
        assert not out.smtp_configured
        api_calls = []
        out._send_via_api = lambda r, h: api_calls.append(r)

        out.save(self._result())
        out.finalize()

        assert api_calls == ["a@b.com"]

    def test_falls_back_to_api_when_smtp_raises(self):
        from crawl4ai.output.email_output import EmailOutput

        out = EmailOutput(to="a@b.com", **SMTP_CREDS)
        api_calls = []

        def _boom(recipient, html):
            raise OSError("connection refused")

        out._send_via_smtp = _boom
        out._send_via_api = lambda r, h: api_calls.append(r)

        out.save(self._result())
        out.finalize()

        assert api_calls == ["a@b.com"], "a failed SMTP send must still attempt delivery"

    def test_smtp_message_is_multipart_with_html(self):
        """The HTML body must survive as an alternative part, not be dropped."""
        from crawl4ai.output.email_output import EmailOutput

        captured = {}

        class FakeServer:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def starttls(self): captured["starttls"] = True
            def login(self, u, p): captured["login"] = (u, p)
            def send_message(self, msg): captured["msg"] = msg

        out = EmailOutput(to="a@b.com", subject="Digest", **SMTP_CREDS)
        import crawl4ai.output.email_output as mod
        original = mod.smtplib.SMTP
        mod.smtplib.SMTP = lambda *a, **k: FakeServer()
        try:
            out._send_via_smtp("a@b.com", "<html><body>hi</body></html>")
        finally:
            mod.smtplib.SMTP = original

        msg = captured["msg"]
        assert captured["starttls"] is True
        assert captured["login"] == ("sender@example.com", "secret")
        assert msg["To"] == "a@b.com"
        assert msg["From"] == "sender@example.com"
        assert msg["Subject"] == "Digest"
        assert "hi" in msg.get_payload()[1].get_payload()

    def test_smtp_credentials_reach_email_backend_from_job_factory(self):
        """create_job_outputs used to accept SMTP params and silently ignore them."""
        from crawl4ai.output.job import create_job_outputs
        from crawl4ai.output.email_output import EmailOutput
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            _, _, backends = create_job_outputs(
                project_root=tmp, title="T", email_to="a@b.com", **SMTP_CREDS
            )
        mailer = next(b for b in backends if isinstance(b, EmailOutput))
        assert mailer.smtp_configured
        assert mailer.smtp_host == "smtp.example.com"
        assert mailer.smtp_from == "sender@example.com", "From should default to the user"
