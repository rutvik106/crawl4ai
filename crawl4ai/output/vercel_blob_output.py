"""Vercel Blob Storage output backend.

Uploads job artifacts (HTML report, JSON results) to Vercel Blob Storage
after local file backends have written them.

Requires:
    - ``vercel`` Python package (pip install vercel)
    - ``BLOB_READ_WRITE_TOKEN`` environment variable set to your Vercel Blob token

Usage::

    from crawl4ai.output.vercel_blob_output import VercelBlobOutput

    backend = VercelBlobOutput(job_id="20260207_210500_a3f2", output_dir="/path/to/output/20260207_210500_a3f2")
    # Call finalize() after local file backends have written their files
    backend.finalize()
    print(backend.uploaded_urls)  # {'report.html': 'https://...', 'results.json': 'https://...'}
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .base import OutputBackend
from ..models import CrawlResult


class VercelBlobOutput(OutputBackend):
    """Uploads job artifacts to Vercel Blob Storage on finalize().

    This backend does not write files itself — it uploads artifacts
    that other backends (e.g. HTMLReportOutput, JsonFileOutput) have
    already written to ``output_dir``.

    Args:
        job_id: The unique job identifier used to namespace blobs.
        output_dir: Local directory where job artifacts reside.
        blob_token: Vercel Blob read-write token. Falls back to the
            ``BLOB_READ_WRITE_TOKEN`` environment variable.
    """

    # Artifacts to upload, in order: (local filename, blob path suffix)
    _ARTIFACTS = [
        ("report.html", "report.html"),
        ("results.json", "results.json"),
    ]

    def __init__(
        self,
        job_id: str,
        output_dir: str,
        blob_token: Optional[str] = None,
    ) -> None:
        self.job_id = job_id
        self.output_dir = output_dir
        self.blob_token = blob_token or os.getenv("BLOB_READ_WRITE_TOKEN", "")
        self.uploaded_urls: Dict[str, str] = {}

    def save(self, result: CrawlResult, metadata: Optional[Dict[str, Any]] = None) -> None:
        # Files are already being written by other backends; nothing to do here.
        pass

    def finalize(self) -> None:
        """Upload artifacts to Vercel Blob Storage."""
        if not self.blob_token:
            print("[vercel_blob] BLOB_READ_WRITE_TOKEN not set — skipping upload")
            return

        try:
            from vercel.blob import BlobClient
        except ImportError:
            print("[vercel_blob] 'vercel' package not installed — skipping upload. "
                  "Run: pip install vercel")
            return

        os.environ.setdefault("BLOB_READ_WRITE_TOKEN", self.blob_token)

        client = BlobClient(token=self.blob_token)

        for local_name, blob_suffix in self._ARTIFACTS:
            local_path = os.path.join(self.output_dir, local_name)
            if not os.path.exists(local_path):
                print(f"[vercel_blob] {local_name} not found, skipping")
                continue

            blob_path = f"crawl4ai/{self.job_id}/{blob_suffix}"
            try:
                with open(local_path, "rb") as fh:
                    data = fh.read()

                uploaded = client.put(
                    blob_path,
                    data,
                    access="public",
                    add_random_suffix=False,
                )
                url = uploaded.url if hasattr(uploaded, "url") else uploaded.get("url", "")
                self.uploaded_urls[local_name] = url
                print(f"[vercel_blob] Uploaded {local_name} → {url}")
            except Exception as exc:
                print(f"[vercel_blob] Failed to upload {local_name}: {exc}")
