"""Tests for shared.describe – metadata formatting and prompt construction."""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from shared.describe import describe_documents

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_llm(text: str):
    """Return a fake LLM Runnable that captures input and returns a fixed AIMessage.

    The returned object is a proper langchain Runnable so it works with
    ``prompt | llm | StrOutputParser()`` chaining.  The captured inputs
    are stored in ``llm.captured`` for test assertions.
    """
    captured: list = []

    def _invoke(messages, **kwargs):
        captured.append(messages)
        return AIMessage(content=text)

    llm = RunnableLambda(_invoke)
    llm.captured = captured  # type: ignore[attr-defined]
    return llm


def _get_human_message_text(mock_llm) -> str:
    """Extract the human message text from the last captured LLM invocation."""
    assert mock_llm.captured, "LLM was never invoked"
    prompt_value = mock_llm.captured[-1]
    # ChatPromptValue has a .messages list
    messages = prompt_value.messages if hasattr(prompt_value, "messages") else list(prompt_value)
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            return msg.content
    return ""


SAMPLE_EXTRACTED = [{"file_name": "test.pdf", "text": "Hello world, this is a test document."}]
SAMPLE_IMAGES = []


# ---------------------------------------------------------------------------
# Metadata block construction
# ---------------------------------------------------------------------------


class TestMetadataBlock:
    """Tests that file_metadata is correctly formatted into the prompt."""

    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="en")
    def test_pdf_metadata_included_in_prompt(self, _mock_lang, mock_get_llm):
        """PDF metadata fields (author, title, creation_date) must appear in the LLM call."""
        mock_llm = _make_mock_llm("### Title\nDescription here.")
        mock_get_llm.return_value = mock_llm

        meta = {
            "test.pdf": {
                "file_type": "pdf",
                "file_name": "test.pdf",
                "page_count": 5,
                "author": "Cara de Nysschen",
                "creator": "Microsoft® Word 2013",
                "creation_date": "2018-04-11T15:09:38+02:00",
                "file_size_bytes": 320240,
                "file_created": "2026-04-15T16:55:34",
                "file_modified": "2026-04-15T16:55:34",
            }
        }

        describe_documents(SAMPLE_EXTRACTED, SAMPLE_IMAGES, language="en", file_metadata=meta)

        human_text = _get_human_message_text(mock_llm)

        assert "=====" in human_text, "Metadata block should be delimited with ====="
        assert "Cara de Nysschen" in human_text
        assert "Microsoft® Word 2013" in human_text
        assert "2018-04-11" in human_text
        assert "page_count" in human_text

    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="en")
    def test_excluded_keys_not_in_metadata(self, _mock_lang, mock_get_llm):
        """Keys in _META_EXCLUDE_KEYS must NOT appear in the metadata section."""
        mock_llm = _make_mock_llm("### Title\nDescription.")
        mock_get_llm.return_value = mock_llm

        meta = {
            "test.pdf": {
                "file_type": "pdf",
                "file_name": "test.pdf",
                "file_size_bytes": 320240,
                "file_created": "2026-04-15T16:55:34",
                "file_modified": "2026-04-15T16:55:34",
                "author": "Jane Doe",
                "exif": {"Make": "Canon", "raw_binary": "..."},
                "web_detection": {"entities": []},
                "identification": {"name": "someone"},
            }
        }

        describe_documents(SAMPLE_EXTRACTED, SAMPLE_IMAGES, language="en", file_metadata=meta)

        human_text = _get_human_message_text(mock_llm)

        # Excluded keys should not be in the metadata JSON block
        # (file_name appears in the content section, but not in the ===== metadata block)
        metadata_part = human_text.split("=====")[1] if "=====" in human_text else ""
        assert '"file_size_bytes"' not in metadata_part
        assert '"file_created"' not in metadata_part
        assert '"file_modified"' not in metadata_part
        assert '"exif"' not in metadata_part
        assert '"web_detection"' not in metadata_part
        assert '"identification"' not in metadata_part
        # But author should be there
        assert "Jane Doe" in metadata_part

    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="en")
    def test_no_metadata_block_when_none(self, _mock_lang, mock_get_llm):
        """When file_metadata is None, no ===== block should appear."""
        mock_llm = _make_mock_llm("### Title\nDescription.")
        mock_get_llm.return_value = mock_llm

        describe_documents(SAMPLE_EXTRACTED, SAMPLE_IMAGES, language="en", file_metadata=None)

        human_text = _get_human_message_text(mock_llm)
        assert "=====" not in human_text

    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="en")
    def test_no_metadata_block_when_only_excluded_keys(self, _mock_lang, mock_get_llm):
        """If metadata has only excluded keys, no ===== block should appear."""
        mock_llm = _make_mock_llm("### Title\nDescription.")
        mock_get_llm.return_value = mock_llm

        meta = {
            "test.pdf": {
                "file_name": "test.pdf",
                "file_size_bytes": 100,
                "file_created": "2026-01-01",
                "file_modified": "2026-01-01",
            }
        }

        describe_documents(SAMPLE_EXTRACTED, SAMPLE_IMAGES, language="en", file_metadata=meta)

        human_text = _get_human_message_text(mock_llm)
        assert "=====" not in human_text

    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="en")
    def test_image_exif_metadata_included(self, _mock_lang, mock_get_llm):
        """Image EXIF metadata (camera, GPS, date) must appear in the prompt."""
        mock_llm = _make_mock_llm("### Photo\nA beautiful landscape.")
        mock_get_llm.return_value = mock_llm

        extracted = [{"file_name": "photo.jpg", "text": "Image description text"}]
        meta = {
            "photo.jpg": {
                "file_type": "image",
                "file_name": "photo.jpg",
                "file_size_bytes": 500000,
                "file_created": "2026-01-01",
                "file_modified": "2026-01-01",
                "camera_make": "Canon",
                "camera_model": "EOS R5",
                "date_taken": "2024:06:15 14:30:00",
                "gps_latitude": 48.8566,
                "gps_longitude": 2.3522,
                "iso": 400,
            }
        }

        describe_documents(extracted, SAMPLE_IMAGES, language="en", file_metadata=meta)

        human_text = _get_human_message_text(mock_llm)

        assert "Canon" in human_text
        assert "EOS R5" in human_text
        assert "48.8566" in human_text
        assert "2.3522" in human_text
        assert "400" in human_text

    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="en")
    def test_metadata_formatting_error_is_logged_and_skipped(
        self, _mock_lang, mock_get_llm, caplog
    ):
        """If JSON serialization fails for one file, it should be logged and skipped."""
        mock_llm = _make_mock_llm("### Title\nOK.")
        mock_get_llm.return_value = mock_llm

        # Create an object that will fail json.dumps
        class BadValue:
            def __repr__(self):
                raise RuntimeError("cannot repr")

        meta = {
            "bad.pdf": {
                "author": BadValue(),
                "file_type": "pdf",
            },
            "good.pdf": {
                "author": "Good Author",
                "file_type": "pdf",
            },
        }

        with caplog.at_level("WARNING"):
            describe_documents(
                [{"file_name": "good.pdf", "text": "Some text"}],
                [],
                language="en",
                file_metadata=meta,
            )

        human_text = _get_human_message_text(mock_llm)

        # good.pdf metadata should still be present
        assert "Good Author" in human_text
        # A warning should have been logged for bad.pdf
        assert any("bad.pdf" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_returns_empty_when_no_content(self):
        """No extracted text and no images → empty string, no LLM call."""
        result = describe_documents([], [], language="en", file_metadata=None)
        assert result == ""

    def test_returns_empty_when_text_is_blank(self):
        result = describe_documents([{"file_name": "empty.txt", "text": "   "}], [], language="en")
        assert result == ""

    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="en")
    def test_multiple_files_metadata(self, _mock_lang, mock_get_llm):
        """Metadata for multiple files should each get their own [filename] block."""
        mock_llm = _make_mock_llm("### Multiple files\nTwo documents uploaded.")
        mock_get_llm.return_value = mock_llm

        extracted = [
            {"file_name": "a.pdf", "text": "Document A content"},
            {"file_name": "b.pdf", "text": "Document B content"},
        ]
        meta = {
            "a.pdf": {"file_type": "pdf", "author": "Alice", "file_name": "a.pdf"},
            "b.pdf": {"file_type": "pdf", "author": "Bob", "file_name": "b.pdf"},
        }

        describe_documents(extracted, [], language="en", file_metadata=meta)

        human_text = _get_human_message_text(mock_llm)

        assert "[a.pdf]" in human_text
        assert "[b.pdf]" in human_text
        assert "Alice" in human_text
        assert "Bob" in human_text

    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="pl")
    def test_polish_language_uses_polish_prompt(self, _mock_lang, mock_get_llm):
        """When language is 'pl', the Polish prompt should be used."""
        mock_llm = _make_mock_llm("### Tytuł\nOpis po polsku.")
        mock_get_llm.return_value = mock_llm

        describe_documents(SAMPLE_EXTRACTED, SAMPLE_IMAGES, language="pl", file_metadata=None)

        # Verify invoke was called (prompt construction didn't crash)
        assert len(mock_llm.captured) == 1
