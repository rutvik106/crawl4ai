"""Import smoke test in a clean interpreter process."""

import subprocess
import sys


def test_clean_interpreter_public_exports():
    code = r'''
import crawl4ai
from crawl4ai import *  # noqa: F403

for name in crawl4ai.__all__:
    assert hasattr(crawl4ai, name), f"missing export: {name}"

import crawl4ai.output as output
for name in output.__all__:
    assert hasattr(output, name), f"missing output export: {name}"
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
