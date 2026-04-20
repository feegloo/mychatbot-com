"""Tests for PDF image extraction and parallel description pipeline.

Uses the real test PDF: test-files/Nikki-Butler-Ultimate-Guide-To-Scar-Treatments.pdf
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shared.extractors import (
    _NUM_THREADS,
    MIN_IMAGE_SIZE,
    _describe_image,
    _describe_one,
    _extract_and_save_images,
    extract_pdf_images,
)

TEST_PDF = (
    Path(__file__).resolve().parent.parent.parent
    / "test-files"
    / "Nikki-Butler-Ultimate-Guide-To-Scar-Treatments.pdf"
)


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "images"


@pytest.fixture(autouse=True)
def _ensure_output_dir(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)


# ── Sanity checks ───────────────────────────────────────────────────


def test_test_pdf_exists():
    assert TEST_PDF.exists(), f"Test PDF not found: {TEST_PDF}"


def test_num_threads_uses_all_cores():
    expected = os.cpu_count() * 2
    assert expected == _NUM_THREADS


# ── Image extraction (CPU-bound, no API) ────────────────────────────


class TestExtractAndSaveImages:
    def test_extracts_images_from_real_pdf(self, output_dir):
        results = _extract_and_save_images(TEST_PDF, output_dir)
        assert len(results) > 0, "Expected at least one image from test PDF"

    def test_returned_dicts_have_required_keys(self, output_dir):
        results = _extract_and_save_images(TEST_PDF, output_dir)
        required_keys = {"image_path", "image_name", "file_name", "png_bytes", "page"}
        for item in results:
            assert required_keys.issubset(item.keys()), f"Missing keys in {item.keys()}"

    def test_saved_files_are_png(self, output_dir):
        results = _extract_and_save_images(TEST_PDF, output_dir)
        for item in results:
            path = Path(item["image_path"])
            assert path.exists(), f"Image not saved: {path}"
            assert path.suffix == ".png"
            # PNG magic bytes
            header = path.read_bytes()[:8]
            assert header[:4] == b"\x89PNG", f"Not a valid PNG: {path}"

    def test_png_bytes_match_saved_files(self, output_dir):
        results = _extract_and_save_images(TEST_PDF, output_dir)
        for item in results:
            assert item["png_bytes"] == Path(item["image_path"]).read_bytes()

    def test_skips_tiny_images(self, output_dir):
        results = _extract_and_save_images(TEST_PDF, output_dir)
        for item in results:
            assert len(item["png_bytes"]) >= MIN_IMAGE_SIZE

    def test_page_numbers_are_positive(self, output_dir):
        results = _extract_and_save_images(TEST_PDF, output_dir)
        for item in results:
            assert item["page"] >= 1

    def test_file_name_matches_pdf(self, output_dir):
        results = _extract_and_save_images(TEST_PDF, output_dir)
        for item in results:
            assert item["file_name"] == TEST_PDF.name

    def test_image_names_are_unique(self, output_dir):
        results = _extract_and_save_images(TEST_PDF, output_dir)
        names = [r["image_name"] for r in results]
        assert len(names) == len(set(names)), "Duplicate image names"


# ── Description pipeline (mocked API) ───────────────────────────────


class TestDescribeOne:
    @patch("shared.extractors._describe_image", return_value="A photo of scar tissue.")
    def test_returns_description(self, mock_describe):
        item = {
            "image_path": "/tmp/img.png",
            "image_name": "img.png",
            "file_name": "test.pdf",
            "png_bytes": b"\x89PNG fake",
            "page": 1,
        }
        result = _describe_one(item)
        assert result["description"] == "A photo of scar tissue."
        assert "png_bytes" not in result  # cleaned up
        mock_describe.assert_called_once_with(b"\x89PNG fake")

    @patch("shared.extractors._describe_image", side_effect=Exception("API down"))
    def test_fallback_on_api_error(self, mock_describe):
        item = {
            "image_path": "/tmp/img.png",
            "image_name": "img.png",
            "file_name": "test.pdf",
            "png_bytes": b"\x89PNG fake",
            "page": 3,
        }
        result = _describe_one(item)
        assert "page 3" in result["description"]
        assert "test.pdf" in result["description"]


class TestExtractPdfImages:
    @patch("shared.extractors._describe_image", return_value="Mocked description.")
    def test_end_to_end_with_mocked_api(self, mock_describe, output_dir):
        results = extract_pdf_images(TEST_PDF, output_dir)
        assert len(results) > 0
        for r in results:
            assert r["description"] == "Mocked description."
            assert "png_bytes" not in r  # should not leak raw bytes

    @patch("shared.extractors._describe_image", return_value="desc")
    def test_results_sorted_by_page(self, mock_describe, output_dir):
        results = extract_pdf_images(TEST_PDF, output_dir)
        pages = [r["page"] for r in results]
        assert pages == sorted(pages), "Results should be sorted by page"

    @patch("shared.extractors._describe_image", return_value="desc")
    def test_parallel_execution_calls_describe_for_each(self, mock_describe, output_dir):
        results = extract_pdf_images(TEST_PDF, output_dir)
        assert mock_describe.call_count == len(results)

    @patch("shared.extractors._describe_image", return_value="desc")
    def test_output_keys_match_contract(self, mock_describe, output_dir):
        results = extract_pdf_images(TEST_PDF, output_dir)
        expected = {"image_path", "image_name", "file_name", "description", "page"}
        for r in results:
            assert set(r.keys()) == expected

    def test_empty_pdf_returns_empty(self, tmp_path, output_dir):
        """A PDF with no images should return empty list."""
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        # Insert only text, no images
        page.insert_text((72, 72), "Hello, no images here.")
        empty_pdf = tmp_path / "empty.pdf"
        doc.save(str(empty_pdf))
        doc.close()

        results = extract_pdf_images(empty_pdf, output_dir)
        assert results == []


# ── Prompt quality ───────────────────────────────────────────────────


class TestPromptQuality:
    @patch("shared.extractors.get_settings")
    @patch("shared.extractors.OpenAI")
    def test_max_completion_tokens_is_1200(self, mock_openai_cls, mock_settings):
        mock_settings.return_value = MagicMock(
            openai_api_key="test", openai_chat_model="gpt-5.4-mini"
        )
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="desc"))]
        )

        _describe_image(b"fake")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_completion_tokens"] == 1200, "max_completion_tokens should be 1200"

    @patch("shared.extractors.get_settings")
    @patch("shared.extractors.OpenAI")
    def test_prompt_is_ocr_first(self, mock_openai_cls, mock_settings):
        mock_settings.return_value = MagicMock(
            openai_api_key="test", openai_chat_model="gpt-5.4-mini"
        )
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="desc"))]
        )

        _describe_image(b"fake")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        prompt_text = call_kwargs["messages"][0]["content"]
        assert "OCR-first" in prompt_text
        assert "Never translate" in prompt_text
        assert "right-to-left" in prompt_text
