"""Tests for shared.describe – metadata formatting and prompt construction."""

from __future__ import annotations

import math
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
        # 'creator' is in _META_EXCLUDE_KEYS — should NOT appear
        assert "Microsoft® Word 2013" not in human_text
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
    def test_returns_fallback_when_no_content(self):
        """No extracted text and no images → fallback message (not empty)."""
        result = describe_documents([], [], language="en", file_metadata=None)
        assert "has been uploaded" in result["welcome_message"]
        assert "Text extraction was not possible" in result["welcome_message"]

    def test_returns_fallback_when_text_is_blank(self):
        result = describe_documents([{"file_name": "empty.txt", "text": "   "}], [], language="en")
        assert "empty.txt" in result["welcome_message"]
        assert "has been uploaded" in result["welcome_message"]

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


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestInvokeWithRetry:
    """Tests for _invoke_with_retry: exponential backoff on 429 errors."""

    def test_succeeds_on_first_attempt(self):
        from shared.describe import _invoke_with_retry

        chain = RunnableLambda(lambda _: "ok")
        assert _invoke_with_retry(chain, {}, label="test") == "ok"

    @patch("shared.describe.time.sleep")
    def test_retries_on_rate_limit_then_succeeds(self, mock_sleep):
        from shared.describe import _invoke_with_retry

        call_count = 0

        def _invoke(params):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Error code: 429 rate limit exceeded")
            return "recovered"

        chain = RunnableLambda(_invoke)
        result = _invoke_with_retry(chain, {}, label="test")
        assert result == "recovered"
        assert call_count == 3
        # Should have slept twice (before retry 2 and 3)
        assert mock_sleep.call_count == 2

    @patch("shared.describe.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        from shared.describe import _invoke_with_retry, _LLM_MAX_RETRIES

        def _invoke(params):
            raise Exception("429 rate_limit")

        chain = RunnableLambda(_invoke)
        import pytest

        with pytest.raises(Exception, match="429"):
            _invoke_with_retry(chain, {}, label="test")
        assert mock_sleep.call_count == _LLM_MAX_RETRIES

    def test_non_rate_limit_error_raises_immediately(self):
        from shared.describe import _invoke_with_retry

        def _invoke(params):
            raise ValueError("some other error")

        chain = RunnableLambda(_invoke)
        import pytest

        with pytest.raises(ValueError, match="some other error"):
            _invoke_with_retry(chain, {}, label="test")


# ---------------------------------------------------------------------------
# Split+Synthesize strategy
# ---------------------------------------------------------------------------


class TestSplitSynthesizeStrategy:
    """Tests for the split+synthesize path (very large documents)."""

    @patch("shared.describe.time.sleep")
    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="en")
    def test_large_document_triggers_split_strategy(
        self, _mock_lang, mock_get_llm, mock_sleep
    ):
        """Documents exceeding _SPLIT_THRESHOLD should use sequential split+synthesize."""
        from shared.describe import _SPLIT_THRESHOLD, _SPLIT_PART_MAX_CHARS

        mock_llm = _make_mock_llm("## Big Book\nA great summary.")
        mock_get_llm.return_value = mock_llm

        # Create text that exceeds _SPLIT_THRESHOLD
        big_text = "x" * (_SPLIT_THRESHOLD + 1000)
        extracted = [{"file_name": "big.pdf", "text": big_text}]

        result = describe_documents(extracted, [], language="en", file_metadata=None)

        # Should have been called multiple times: once per part + once for synthesis
        expected_parts = math.ceil(len(big_text) / _SPLIT_PART_MAX_CHARS)
        # At least N partial calls + 1 synthesis call
        assert len(mock_llm.captured) >= expected_parts + 1
        assert result["welcome_message"]  # non-empty result

    @patch("shared.describe.time.sleep")
    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="en")
    def test_split_strategy_includes_raw_beginning(
        self, _mock_lang, mock_get_llm, mock_sleep
    ):
        """The synthesis call should include raw text from the beginning of the document."""
        from shared.describe import _SPLIT_THRESHOLD, _SYNTHESIS_RAW_TEXT_CHARS

        mock_llm = _make_mock_llm("## Summary\nFinal result.")
        mock_get_llm.return_value = mock_llm

        # Use distinct content at the beginning so we can check it appears
        marker = "UNIQUE_BEGINNING_MARKER_12345"
        big_text = marker + "y" * _SPLIT_THRESHOLD
        extracted = [{"file_name": "big.pdf", "text": big_text}]

        describe_documents(extracted, [], language="en", file_metadata=None)

        # The last LLM call is the synthesis — check it has raw text
        last_call = mock_llm.captured[-1]
        messages = last_call.messages if hasattr(last_call, "messages") else list(last_call)
        human_text = ""
        for msg in messages:
            if hasattr(msg, "type") and msg.type == "human":
                human_text = msg.content
                break
        assert marker in human_text, "Synthesis prompt should contain raw beginning text"

    @patch("shared.describe.time.sleep")
    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="en")
    def test_split_strategy_sequential_with_delays(
        self, _mock_lang, mock_get_llm, mock_sleep
    ):
        """Split strategy should add inter-call delays between sequential LLM calls."""
        from shared.describe import _SPLIT_THRESHOLD, _SPLIT_PART_MAX_CHARS

        mock_llm = _make_mock_llm("## Result\nSummary.")
        mock_get_llm.return_value = mock_llm

        big_text = "z" * (_SPLIT_THRESHOLD + 1000)
        extracted = [{"file_name": "big.pdf", "text": big_text}]

        describe_documents(extracted, [], language="en", file_metadata=None)

        expected_parts = math.ceil(len(big_text) / _SPLIT_PART_MAX_CHARS)
        # Should have (N-1) sleeps between N sequential part calls
        assert mock_sleep.call_count >= expected_parts - 1


# ---------------------------------------------------------------------------
# Response parsing (welcome message + suggested questions)
# ---------------------------------------------------------------------------


class TestWholeBookStrategy:
    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="en")
    def test_whole_book_strategy_keeps_tail_text_when_under_token_limit(
        self, _mock_lang, mock_get_llm
    ):
        from shared.describe import _DESCRIBE_MAX_CONTENT_CHARS

        marker = "WHOLE_BOOK_TAIL_MARKER_98765"
        text = ("intro " * 25000) + marker
        assert len(text) > _DESCRIBE_MAX_CONTENT_CHARS

        mock_llm = _make_mock_llm("## Whole Book\nSummary.")
        mock_get_llm.return_value = mock_llm

        describe_documents(
            [{"file_name": "book.pdf", "text": text}],
            [],
            language="en",
            file_metadata={"book.pdf": {"page_count": 180}},
        )

        human_text = _get_human_message_text(mock_llm)
        assert marker in human_text

    @patch("shared.describe.get_llm")
    @patch("shared.describe.detect_language", return_value="en")
    def test_large_book_with_chapters_uses_compaction_and_synthesis(
        self, _mock_lang, mock_get_llm
    ):
        from shared.describe import _WHOLE_BOOK_MAX_ESTIMATED_TOKENS

        mock_llm = _make_mock_llm("## Large Book\nSummary.")
        mock_get_llm.return_value = mock_llm

        pages = []
        for page in range(1, 301):
            pages.append(f"# Page {page}\n\n" + (f"page {page} text " * 250))
        text = "\n\n".join(pages)
        assert len(text) // 4 > _WHOLE_BOOK_MAX_ESTIMATED_TOKENS

        chapters = [
            {"title": "One", "start_page": 1, "end_page": 100},
            {"title": "Two", "start_page": 101, "end_page": 200},
            {"title": "Three", "start_page": 201, "end_page": 300},
        ]

        result = describe_documents(
            [{"file_name": "book.pdf", "text": text}],
            [],
            language="en",
            file_metadata={"book.pdf": {"page_count": 300}},
            chapters=chapters,
        )

        assert result["welcome_message"]
        assert len(mock_llm.captured) >= 2


class TestParseDescribeResponse:
    """Tests for _parse_describe_response: extracting inline [action:...] markers."""

    def test_parses_welcome_and_actions(self):
        from shared.describe import _parse_describe_response

        response = (
            "## My Book - Author\n\nGreat book about stuff.\n\n"
            "Expert insight here.\n\n"
            "[action:What is the main theme?] [action:Who is the protagonist?] "
            "[action:When was it written?] [action:Create a quiz 🧠] "
            "[action:Write inspired chapter ✏️]"
        )
        welcome, questions = _parse_describe_response(response)
        # Action markers MUST stay inline in the welcome content — the
        # frontend renders them there.
        assert "## My Book - Author" in welcome
        assert "Expert insight here." in welcome
        assert "[action:What is the main theme?]" in welcome
        assert "[action:Create a quiz 🧠]" in welcome
        assert len(questions) == 5
        assert questions[0] == "What is the main theme?"
        assert questions[3] == "Create a quiz 🧠"

    def test_returns_empty_actions_when_no_markers(self):
        from shared.describe import _parse_describe_response

        response = "## Title\n\nJust a welcome message, no actions."
        welcome, questions = _parse_describe_response(response)
        assert welcome == response
        assert questions == []

    def test_recovers_bare_action_row_without_wrappers(self):
        """When the model forgets to wrap the final action row in
        [action:...] markers (emitting plain prose like ``What happens
        to Bran? ... Generate image inspired by Westeros 🎨 Write chapter
        ✏️``), the parser should recover the fragments and re-embed them
        as proper markers so the frontend renders clickable pills."""
        from shared.describe import _parse_describe_response

        response = (
            "## A Game of Thrones - George R. R. Martin\n\n"
            "📖 Great fantasy book.\n\n"
            "💡 The novel's power lies in fusing family tragedy with dynastic conflict.\n\n"
            "What happens to Bran after the fall? Who is George R. R. Martin? "
            "How does Daenerys gain dragons? Generate image inspired by Westeros 🎨 "
            "Write inspired chapter like George R. R. Martin ✏️ "
            "Create a quiz from the key facts 🧠 "
            "Summarize the Stark family conflicts 📝"
        )
        welcome, questions = _parse_describe_response(response)
        assert len(questions) >= 5
        assert any("Bran" in q for q in questions)
        assert any("🎨" in q for q in questions)
        assert "[action:" in welcome
        # The prose action row should have been stripped from the welcome
        # body and re-emitted as a marker line at the very end.
        assert welcome.rstrip().endswith("]")

    def test_describe_documents_returns_dict_with_inline_actions(self):
        """describe_documents should return a DescribeResult whose
        welcome_message carries [action:...] markers inline (single source
        of truth for the frontend)."""
        mock_llm = _make_mock_llm(
            "## Test - Author\n\nDescription.\n\nInsight.\n\n"
            "[action:Q1?] [action:Q2?] [action:Q3?] "
            "[action:Action 1 🧠] [action:Action 2 ✏️]"
        )
        with patch("shared.describe.get_llm", return_value=mock_llm), \
             patch("shared.describe.detect_language", return_value="en"):
            result = describe_documents(
                SAMPLE_EXTRACTED, SAMPLE_IMAGES, language="en", file_metadata=None
            )
        assert isinstance(result, dict)
        assert "## Test - Author" in result["welcome_message"]
        assert "[action:Q1?]" in result["welcome_message"]
        assert len(result["suggested_questions"]) >= 3
