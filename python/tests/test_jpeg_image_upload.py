"""Tests for standalone JPEG image upload and OCR extraction.

Covers the 22.jpg use-case: a scanned page uploaded as a .jpg file where
the vision model transcribes the text (possibly Polish or other non-ASCII
language) back as a searchable string.

Validated behaviours:
  - .jpg dispatches to extract_image, not extract_plain_text / extract_pdf
  - MIME type sent to the Vision API is "image/jpeg" (not "image/png")
  - The standalone-image prompt is used (includes people-appearance instructions)
  - Extracted text is returned verbatim — no translation or summarisation
  - process_standalone_file builds a complete FileProcessingResult:
      full_text, all_images entry, all_chunks
  - Vision API failure falls back to a safe "Image file: <name>" string
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from shared.extractors import (
    _MIME_TYPES,
    IMAGE_EXTENSIONS,
    extract_image,
    extract_text,
)
from shared.page_worker import process_standalone_file

# ── Helpers ──────────────────────────────────────────────────────────


def _make_minimal_jpeg(path: Path) -> bytes:
    """Write a tiny but valid JPEG file and return its bytes."""
    from PIL import Image as PILImage

    img = PILImage.new("RGB", (10, 10), color=(200, 100, 50))
    img.save(path, format="JPEG")
    return path.read_bytes()


# ── MIME type and extension registry ─────────────────────────────────


class TestJpegMimeMapping:
    def test_jpg_is_in_image_extensions(self):
        assert ".jpg" in IMAGE_EXTENSIONS

    def test_jpeg_is_in_image_extensions(self):
        assert ".jpeg" in IMAGE_EXTENSIONS

    def test_jpg_mime_is_jpeg(self):
        assert _MIME_TYPES[".jpg"] == "image/jpeg"

    def test_jpeg_mime_is_jpeg(self):
        assert _MIME_TYPES[".jpeg"] == "image/jpeg"

    def test_png_mime_differs_from_jpeg(self):
        # Regression: PNG uploads must not accidentally send image/jpeg
        assert _MIME_TYPES[".png"] == "image/png"


# ── extract_image — vision API call ──────────────────────────────────


class TestExtractImageJpeg:
    @patch("shared.extractors.get_settings")
    @patch("shared.extractors.OpenAI")
    def test_jpeg_sends_image_jpeg_mime_type(self, mock_openai_cls, mock_settings, tmp_path):
        """Vision API must receive image/jpeg content-type for .jpg files."""
        mock_settings.return_value = MagicMock(
            openai_api_key="test",
            openai_chat_model="gpt-4o",
            openai_reasoning_effort="low",
        )
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Extracted Polish text"))],
            usage=MagicMock(
                prompt_tokens=10, completion_tokens=5, total_tokens=15,
                prompt_tokens_details=None,
            ),
        )

        jpg_path = tmp_path / "22.jpg"
        _make_minimal_jpeg(jpg_path)

        result = extract_image(jpg_path)

        assert result == "Extracted Polish text"
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        user_content = call_kwargs["messages"][1]["content"]
        image_part = next(c for c in user_content if c.get("type") == "image_url")
        assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")

    @patch("shared.extractors.get_settings")
    @patch("shared.extractors.OpenAI")
    def test_jpeg_uses_standalone_image_prompt(self, mock_openai_cls, mock_settings, tmp_path):
        """Standalone JPEG must use the standalone-image prompt, not the OCR-only one."""
        mock_settings.return_value = MagicMock(
            openai_api_key="test",
            openai_chat_model="gpt-4o",
            openai_reasoning_effort="low",
        )
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="some text"))],
            usage=MagicMock(
                prompt_tokens=5, completion_tokens=3, total_tokens=8,
                prompt_tokens_details=None,
            ),
        )

        jpg_path = tmp_path / "scan.jpg"
        _make_minimal_jpeg(jpg_path)

        extract_image(jpg_path)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        system_content = call_kwargs["messages"][0]["content"]
        # The standalone prompt includes people-appearance instructions
        assert "standalone image uploads" in system_content

    @patch("shared.extractors.get_settings")
    @patch("shared.extractors.OpenAI")
    def test_polish_text_returned_verbatim(self, mock_openai_cls, mock_settings, tmp_path):
        """Text extracted by the vision model must be returned unchanged."""
        polish_text = (
            "Biblioteka doktora Efekta, licząca kilka tysięcy egzemplarzy, "
            "zajmowała dwie ściany jadalni."
        )
        mock_settings.return_value = MagicMock(
            openai_api_key="test",
            openai_chat_model="gpt-4o",
            openai_reasoning_effort="low",
        )
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=polish_text))],
            usage=MagicMock(
                prompt_tokens=20, completion_tokens=40, total_tokens=60,
                prompt_tokens_details=None,
            ),
        )

        jpg_path = tmp_path / "22.jpg"
        _make_minimal_jpeg(jpg_path)

        result = extract_image(jpg_path)

        assert result == polish_text

    @patch("shared.extractors.OpenAI", side_effect=Exception("API timeout"))
    def test_vision_failure_returns_safe_fallback(self, _mock_openai_cls, tmp_path):
        """If the vision API fails, extract_image must not raise — returns filename fallback."""
        jpg_path = tmp_path / "22.jpg"
        _make_minimal_jpeg(jpg_path)

        result = extract_image(jpg_path)

        assert result == "Image file: 22.jpg"


# ── extract_text dispatch ─────────────────────────────────────────────


class TestExtractTextDispatchJpeg:
    @patch("shared.extractors.extract_image")
    def test_jpg_dispatches_to_extract_image(self, mock_extract_image, tmp_path):
        """.jpg extension must be routed to extract_image, not plain-text or PDF."""
        mock_extract_image.return_value = "mocked image text"

        jpg_path = tmp_path / "document.jpg"
        _make_minimal_jpeg(jpg_path)

        result = extract_text(str(jpg_path))

        mock_extract_image.assert_called_once()
        assert result == "mocked image text"

    @patch("shared.extractors.extract_image")
    def test_jpeg_extension_also_dispatches_to_extract_image(self, mock_extract_image, tmp_path):
        """.jpeg variant must behave identically to .jpg."""
        mock_extract_image.return_value = "mocked jpeg text"

        jpeg_path = tmp_path / "document.jpeg"
        _make_minimal_jpeg(jpeg_path)

        result = extract_text(str(jpeg_path))

        mock_extract_image.assert_called_once()
        assert result == "mocked jpeg text"


# ── process_standalone_file integration ─────────────────────────────


class TestProcessStandaloneFileJpeg:
    @patch("shared.page_worker.extract_text")
    def test_full_text_populated_from_vision_result(self, mock_extract_text, tmp_path):
        """full_text must contain the vision model's OCR output."""
        extracted = "PRAWDZIWA HISTORIA\n\nBiblioteka doktora Efekta..."
        mock_extract_text.return_value = extracted

        jpg_path = tmp_path / "22.jpg"
        _make_minimal_jpeg(jpg_path)

        result = process_standalone_file(str(jpg_path), conversation_id="conv-test-1")

        assert result.full_text == extracted

    @patch("shared.page_worker.extract_text")
    def test_all_images_entry_created_for_jpeg(self, mock_extract_text, tmp_path):
        """A JPEG upload must register itself in all_images for thumbnail display."""
        mock_extract_text.return_value = "some OCR text"

        jpg_path = tmp_path / "22.jpg"
        _make_minimal_jpeg(jpg_path)

        result = process_standalone_file(str(jpg_path), conversation_id="conv-test-2")

        assert len(result.all_images) == 1
        img_entry = result.all_images[0]
        assert img_entry["file_name"] == "22.jpg"
        assert img_entry["description"] == "some OCR text"

    @patch("shared.page_worker.extract_text")
    def test_chunks_created_from_extracted_text(self, mock_extract_text, tmp_path):
        """Extracted text must be chunked so it can be indexed in the vector store."""
        # Use enough text to guarantee at least one chunk
        mock_extract_text.return_value = "word " * 200

        jpg_path = tmp_path / "22.jpg"
        _make_minimal_jpeg(jpg_path)

        result = process_standalone_file(str(jpg_path), conversation_id="conv-test-3")

        assert len(result.all_chunks) >= 1

    @patch("shared.page_worker.extract_text")
    def test_total_pages_is_one_for_standalone_image(self, mock_extract_text, tmp_path):
        """A standalone image counts as exactly one page."""
        mock_extract_text.return_value = "text"

        jpg_path = tmp_path / "22.jpg"
        _make_minimal_jpeg(jpg_path)

        result = process_standalone_file(str(jpg_path), conversation_id="conv-test-4")

        assert result.total_pages == 1
        assert len(result.page_results) == 1

    @patch("shared.page_worker.extract_text")
    def test_no_errors_on_successful_extraction(self, mock_extract_text, tmp_path):
        """Successful JPEG processing must produce an error-free result."""
        mock_extract_text.return_value = "clean OCR output"

        jpg_path = tmp_path / "22.jpg"
        _make_minimal_jpeg(jpg_path)

        result = process_standalone_file(str(jpg_path), conversation_id="conv-test-5")

        assert result.errors == []
