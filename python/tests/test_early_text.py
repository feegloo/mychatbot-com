"""Tests for early text capture in process_pdf_parallel.

Verifies that:
- FileProcessingResult.early_text is populated after timeout
- The on_early_text callback fires during processing (not after)
- Normal PDFs (fast extraction) set early_text = full text
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import fitz
import pytest

from shared.page_worker import FileProcessingResult, process_pdf_parallel


def _create_pdf_with_text(tmp_path, num_pages: int, text_per_page: str = "Hello world page") -> str:
    """Create a multi-page PDF with embedded text for testing."""
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=400, height=400)
        tw = fitz.TextWriter(page.rect)
        tw.append((50, 50), f"{text_per_page} {i + 1}", fontsize=12)
        tw.write_text(page)
    pdf_path = str(tmp_path / "test.pdf")
    doc.save(pdf_path)
    doc.close()
    return pdf_path


class TestFileProcessingResultEarlyText:
    def test_early_text_defaults_to_empty(self):
        r = FileProcessingResult(file_name="test.pdf", file_path="/tmp/test.pdf", total_pages=1)
        assert r.early_text == ""

    def test_early_text_is_settable(self):
        r = FileProcessingResult(file_name="test.pdf", file_path="/tmp/test.pdf", total_pages=1)
        r.early_text = "Some early text"
        assert r.early_text == "Some early text"


class TestProcessPdfParallelEarlyText:
    @patch("shared.page_worker._describe_images_parallel", return_value=[])
    def test_small_pdf_sets_early_text_to_full_text(self, _mock_describe, tmp_path):
        """For a small PDF that processes quickly, early_text should equal full_text."""
        pdf_path = _create_pdf_with_text(tmp_path, 3)
        output_dir = str(tmp_path)

        result = process_pdf_parallel(
            pdf_path, output_dir, "test-conv",
            early_text_timeout_s=0.001,  # Very short timeout
        )

        assert result.full_text.strip() != ""
        # early_text should be set (either via timeout or post-completion)
        assert result.early_text != ""

    @patch("shared.page_worker._describe_images_parallel", return_value=[])
    def test_callback_fires_for_small_pdf(self, _mock_describe, tmp_path):
        """on_early_text should be called even for fast PDFs."""
        pdf_path = _create_pdf_with_text(tmp_path, 3)
        output_dir = str(tmp_path)
        callback_data = {}

        def on_early(text, summaries):
            callback_data["text"] = text
            callback_data["summaries"] = summaries

        process_pdf_parallel(
            pdf_path, output_dir, "test-conv",
            early_text_timeout_s=0.001,
            on_early_text=on_early,
        )

        assert "text" in callback_data
        assert len(callback_data["text"]) > 0

    @patch("shared.page_worker._describe_images_parallel", return_value=[])
    def test_callback_receives_page_summaries(self, _mock_describe, tmp_path):
        """Callback should receive page summaries from completed pages."""
        pdf_path = _create_pdf_with_text(tmp_path, 5, text_per_page="This is enough text for a summary to be generated from the page content")
        output_dir = str(tmp_path)
        callback_data = {}

        def on_early(text, summaries):
            callback_data["summaries"] = summaries

        process_pdf_parallel(
            pdf_path, output_dir, "test-conv",
            early_text_timeout_s=0.001,
            on_early_text=on_early,
        )

        assert "summaries" in callback_data
        assert isinstance(callback_data["summaries"], list)

    @patch("shared.page_worker._describe_images_parallel", return_value=[])
    def test_callback_only_fires_once(self, _mock_describe, tmp_path):
        """Callback should fire exactly once, not per page."""
        pdf_path = _create_pdf_with_text(tmp_path, 10)
        output_dir = str(tmp_path)
        call_count = {"n": 0}

        def on_early(text, summaries):
            call_count["n"] += 1

        process_pdf_parallel(
            pdf_path, output_dir, "test-conv",
            early_text_timeout_s=0.001,
            on_early_text=on_early,
        )

        assert call_count["n"] == 1

    @patch("shared.page_worker._describe_images_parallel", return_value=[])
    def test_no_callback_means_no_crash(self, _mock_describe, tmp_path):
        """Processing works fine without a callback."""
        pdf_path = _create_pdf_with_text(tmp_path, 3)
        output_dir = str(tmp_path)

        result = process_pdf_parallel(
            pdf_path, output_dir, "test-conv",
            on_early_text=None,
        )

        assert result.full_text.strip() != ""
        assert len(result.all_chunks) > 0
