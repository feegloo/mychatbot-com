"""Tests for describe_url and the quiz chain with mocked LLM.

Uses RunnableLambda pattern (same as test_describe.py) so no real API calls.
Covers: describe_url language selection, quiz chain invocation via mocked LLM.
"""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda


def _make_mock_llm(text: str):
    """Return a fake LLM Runnable that always replies with `text`."""
    captured: list = []

    def _invoke(messages, **kwargs):
        captured.append(messages)
        return AIMessage(content=text)

    llm = RunnableLambda(_invoke)
    llm.captured = captured  # type: ignore[attr-defined]
    return llm


# ---------------------------------------------------------------------------
# describe_url — integration with mocked LLM
# ---------------------------------------------------------------------------


class TestDescribeUrl:
    @patch("shared.url_fetch.get_llm")
    def test_returns_string(self, mock_get_llm):
        mock_get_llm.return_value = _make_mock_llm("## Wikipedia\nA free encyclopedia.")
        from shared.url_fetch import describe_url

        result = describe_url("https://en.wikipedia.org", "<html><p>Knowledge</p></html>")
        assert isinstance(result, str)
        assert "Wikipedia" in result

    @patch("shared.url_fetch.get_llm")
    @patch("shared.url_fetch.detect_language", return_value="en")
    def test_uses_detected_language_en(self, _mock_lang, mock_get_llm):
        """When no language override → auto-detects from visible text."""
        llm = _make_mock_llm("## Site\nEnglish description.")
        mock_get_llm.return_value = llm
        from shared.url_fetch import describe_url

        result = describe_url("https://example.com", "<p>Hello world</p>")
        assert result == "## Site\nEnglish description."

    @patch("shared.url_fetch.get_llm")
    def test_language_override_bypasses_detection(self, mock_get_llm):
        llm = _make_mock_llm("## Strona\nOpis po polsku.")
        mock_get_llm.return_value = llm
        from shared.url_fetch import describe_url

        result = describe_url("https://example.com", "<p>something</p>", language="pl")
        assert "Opis po polsku" in result

    @patch("shared.url_fetch.get_llm")
    @patch("shared.url_fetch.detect_language", return_value="pl")
    def test_polish_detection_uses_pl_prompt(self, _mock_lang, mock_get_llm):
        llm = _make_mock_llm("## Portal\nPolski opis.")
        mock_get_llm.return_value = llm
        from shared.url_fetch import describe_url

        result = describe_url("https://onet.pl", "<p>Wiadomości</p>")
        assert "Polski opis" in result

        # The captured prompt should mention Polish instructions
        prompt_value = llm.captured[-1]
        messages = prompt_value.messages if hasattr(prompt_value, "messages") else list(prompt_value)
        system_text = next(
            (m.content for m in messages if hasattr(m, "type") and m.type == "system"), ""
        )
        assert "analizujesz" in system_text.lower() or "polsku" in system_text.lower()

    @patch("shared.url_fetch.get_llm")
    @patch("shared.url_fetch.detect_language", return_value="en")
    def test_html_truncated_to_max_chars(self, _mock_lang, mock_get_llm):
        """Oversized HTML is trimmed to _MAX_HTML_CHARS before sending to LLM."""
        from shared.url_fetch import _MAX_HTML_CHARS, describe_url

        llm = _make_mock_llm("## Site\nDesc.")
        mock_get_llm.return_value = llm

        huge_html = "<p>" + "x" * (_MAX_HTML_CHARS + 10_000) + "</p>"
        describe_url("https://example.com", huge_html)

        prompt_value = llm.captured[-1]
        messages = prompt_value.messages if hasattr(prompt_value, "messages") else list(prompt_value)
        human_text = next(
            (m.content for m in messages if hasattr(m, "type") and m.type == "human"), ""
        )
        # The HTML passed to the LLM must not exceed max chars (+some prompt overhead)
        assert len(human_text) <= _MAX_HTML_CHARS + 500

    @patch("shared.url_fetch.get_llm")
    @patch("shared.url_fetch.detect_language", return_value="en")
    def test_url_included_in_human_message(self, _mock_lang, mock_get_llm):
        llm = _make_mock_llm("## Site\nDesc.")
        mock_get_llm.return_value = llm
        from shared.url_fetch import describe_url

        describe_url("https://myspecificsite.com/page", "<p>content</p>")

        prompt_value = llm.captured[-1]
        messages = prompt_value.messages if hasattr(prompt_value, "messages") else list(prompt_value)
        human_text = next(
            (m.content for m in messages if hasattr(m, "type") and m.type == "human"), ""
        )
        assert "myspecificsite.com/page" in human_text


# ---------------------------------------------------------------------------
# _format_welcome_messages  (rag.py utility)
# ---------------------------------------------------------------------------


class TestFormatWelcomeMessages:
    def setup_method(self):
        from shared.rag import _format_welcome_messages

        self.fmt = _format_welcome_messages

    def test_none_returns_placeholder(self):
        assert self.fmt(None) == "(no file descriptions available)"

    def test_empty_list_returns_placeholder(self):
        assert self.fmt([]) == "(no file descriptions available)"

    def test_single_message_returned_as_is(self):
        assert self.fmt(["Single file description"]) == "Single file description"

    def test_multiple_messages_numbered(self):
        result = self.fmt(["First doc", "Second doc"])
        assert "[Upload 1]" in result
        assert "[Upload 2]" in result
        assert "First doc" in result
        assert "Second doc" in result

    def test_multiple_messages_separated(self):
        result = self.fmt(["A", "B", "C"])
        parts = result.split("\n\n")
        assert len(parts) == 3

    def test_three_messages_numbered_correctly(self):
        result = self.fmt(["One", "Two", "Three"])
        assert "[Upload 3]" in result


# ---------------------------------------------------------------------------
# Quiz chain integration test (mocked LLM via get_llm patch)
# ---------------------------------------------------------------------------


class TestQuizChainMocked:
    @patch("shared.rag.get_llm")
    def test_quiz_chain_invoked_with_question(self, mock_get_llm):
        """When _is_quiz_request matches, quiz chain should use QUIZ_PROMPT."""

        quiz_answer = "[quiz:{...}] [action:Quiz A 🧠] [action:Quiz B 🧠]"
        mock_get_llm.return_value = _make_mock_llm(quiz_answer)

        from shared.rag import _is_quiz_request

        assert _is_quiz_request("give me a quiz about the Roman Empire")

    def test_quiz_prompt_format_does_not_raise(self):
        """QUIZ_PROMPT.format_messages must work with all expected variables."""
        from shared.prompts import QUIZ_PROMPT

        msgs = QUIZ_PROMPT.format_messages(
            raw_text="Rome was founded in 753 BC.",
            page_summaries="Page 1 summary",
            welcome_messages="Uploaded: roman.pdf",
            chat_history="User: Tell me about Rome.",
            question="Quiz me on Roman history",
            context="[Source 1] File: roman.pdf | Similarity: 0.95\n\"Rome was a republic.\"",
            conversation_language_name="English",
            conversation_language_code="en",
            num_questions=5,
        )
        assert len(msgs) == 2
        human_content = msgs[1].content
        assert "Quiz me on Roman history" in human_content
        assert "753 BC" in human_content

    def test_quiz_prompt_system_contains_action_rules(self):
        """Quiz system prompt must contain the action button rules (already replaced)."""
        from shared.prompts import QUIZ_PROMPT

        system_template = QUIZ_PROMPT.messages[0].prompt.template
        assert "[action:" in system_template
        assert "🧠" in system_template
        assert "<<QUIZ_ACTIONS>>" not in system_template
