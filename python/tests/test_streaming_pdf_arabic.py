"""Integration test for streaming OCR pipeline on Arabic Mathnawi (10-page cut).

Verifies the hybrid algorithm that replaced Cloud Run Jobs dispatch:
- Pages are parsed in-process
- Sparse pages are OCR'd in a thread pool (parallel, like JS async/await)
- Each completed page invokes on_page_ready callback immediately
- OCR-heavy PDFs are flagged via is_heavy_ocr

This test hits OpenAI Vision. It is skipped automatically when OPENAI_API_KEY
is not set (CI without secrets) or when the test file is unavailable.

Run locally:
    cd python && python3.11 -m pytest tests/test_streaming_pdf_arabic.py -v -s
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from shared.streaming_pdf import (
    PageOutcome,
    StreamingPdfResult,
    process_pdf_streaming,
)

PDF_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "test-files"
    / "54_Mathnawi_Arabic01-1-10.pdf"
)

pytestmark = [
    pytest.mark.skipif(
        not PDF_PATH.exists(),
        reason=f"Test PDF not found at {PDF_PATH}",
    ),
    pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set; skipping live OCR integration test",
    ),
]


class TestStreamingPdfArabic:
    """End-to-end: stream the 10-page Arabic Mathnawi through OCR."""

    def test_process_pdf_streaming_emits_per_page_and_flags_heavy_ocr(self):
        outcomes: list[PageOutcome] = []
        lock = threading.Lock()
        progress_events: list[tuple[int, int]] = []

        def on_page_ready(outcome: PageOutcome) -> None:
            with lock:
                outcomes.append(outcome)

        def on_progress(parsed: int, total: int) -> None:
            progress_events.append((parsed, total))

        result: StreamingPdfResult = process_pdf_streaming(
            str(PDF_PATH),
            conversation_id="test-mathnawi-arabic",
            on_page_ready=on_page_ready,
            on_progress=on_progress,
        )

        # Exactly one outcome per page of the 10-page cut.
        assert result.total_pages == 10
        assert len(outcomes) == 10
        assert len(result.pages) == 10

        # Page numbers are 1..10 (no gaps, no duplicates).
        page_nrs = sorted(o.page_nr for o in outcomes)
        assert page_nrs == list(range(1, 11))

        # Arabic Mathnawi is scanned → OCR should dominate.
        assert result.ocr_page_count >= 8, (
            f"Expected mostly-OCR pages, got {result.ocr_page_count}/10"
        )
        assert result.is_heavy_ocr is True

        # Progress callback was invoked — final event reports all pages done.
        assert progress_events, "on_progress was never called"
        assert progress_events[-1] == (10, 10)

        # At least one successful page has non-empty text so the full_text
        # property (used for welcome regen) is non-trivial.
        successful = [o for o in outcomes if o.source != "failed" and o.text.strip()]
        assert successful, "All pages failed — OCR pipeline broken"
        assert result.full_text.strip(), "full_text must be non-empty for welcome regen"

    def test_process_pdf_streaming_survives_page_failures(self, monkeypatch):
        """Simulate OCR failures and confirm the pipeline continues."""

        # Force every sparse page through a stubbed OCR that fails, to verify
        # failed pages are recorded as source='failed' without aborting the run.
        def _stub_ocr(*args, **kwargs):
            raise RuntimeError("simulated OCR failure")

        monkeypatch.setattr("shared.streaming_pdf.ocr_pdf_page", _stub_ocr)

        outcomes: list[PageOutcome] = []
        lock = threading.Lock()

        def on_page_ready(outcome: PageOutcome) -> None:
            with lock:
                outcomes.append(outcome)

        result = process_pdf_streaming(
            str(PDF_PATH),
            conversation_id="test-mathnawi-arabic-failure",
            on_page_ready=on_page_ready,
        )

        assert result.total_pages == 10
        # Every scanned page should fail but the processor must still emit
        # a PageOutcome for it so recovery + reporting work.
        assert len(outcomes) == 10
        failed = [o for o in outcomes if o.source == "failed"]
        assert len(failed) == result.failed_page_count
        # full_text skips failed pages rather than raising.
        _ = result.full_text
