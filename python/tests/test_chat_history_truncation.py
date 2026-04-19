"""Tests for token-aware chat history truncation in _format_chat_history."""

from shared.rag import _MAX_CHAT_HISTORY_TOKENS, _count_tokens, _format_chat_history


def _make_msg(role: str, content: str, timestamp: str = "") -> dict:
    msg = {"role": role, "content": content}
    if timestamp:
        msg["timestamp"] = timestamp
    return msg


def _make_exchange(num: int, q: str = "short question", a: str = "short answer") -> list[dict]:
    return [
        _make_msg("user", f"{q} #{num}", f"2025-01-01T00:0{num % 10}:00Z"),
        _make_msg("assistant", f"{a} #{num}"),
    ]


class TestCountTokens:
    def test_empty_string(self):
        assert _count_tokens("") == 0

    def test_simple_text(self):
        tokens = _count_tokens("Hello, world!")
        assert 2 <= tokens <= 5

    def test_long_text(self):
        text = "word " * 1000
        tokens = _count_tokens(text)
        assert 900 <= tokens <= 1100


class TestFormatChatHistoryBasic:
    def test_none_history(self):
        assert _format_chat_history(None) == "(no previous conversation)"

    def test_empty_history(self):
        assert _format_chat_history([]) == "(no previous conversation)"

    def test_single_exchange(self):
        history = _make_exchange(1)
        result = _format_chat_history(history)
        assert "[User Question #1]" in result
        assert "[Assistant Answer #1]" in result
        assert "short question #1" in result
        assert "short answer #1" in result

    def test_preserves_timestamps(self):
        history = [_make_msg("user", "q", "2025-06-01T10:00:00Z")]
        result = _format_chat_history(history)
        assert "2025-06-01T10:00:00Z" in result

    def test_long_assistant_truncated_at_3000_chars(self):
        long_content = "x" * 5000
        history = [_make_msg("user", "q"), _make_msg("assistant", long_content)]
        result = _format_chat_history(history)
        assert "... (truncated)" in result
        assert "x" * 3001 not in result


class TestFormatChatHistoryTruncation:
    def test_short_history_not_truncated(self):
        history = []
        for i in range(5):
            history.extend(_make_exchange(i + 1))
        result = _format_chat_history(history)
        assert "omitted" not in result
        assert "[User Question #1]" in result
        assert "[User Question #5]" in result

    def test_massive_history_triggers_truncation(self):
        # Each exchange: ~200 tokens of content → 200 exchanges = ~40k tokens
        history = []
        for i in range(200):
            history.extend([
                _make_msg("user", f"Question number {i}: " + "elaborate context " * 30),
                _make_msg("assistant", f"Answer number {i}: " + "detailed response " * 50),
            ])

        result = _format_chat_history(history)
        assert "omitted" in result
        # Most recent exchanges should be preserved
        assert "Answer number 199" in result

    def test_truncation_drops_oldest_keeps_newest(self):
        history = []
        for i in range(300):
            history.extend([
                _make_msg("user", f"Q{i}: " + "padding " * 40),
                _make_msg("assistant", f"A{i}: " + "padding " * 40),
            ])

        result = _format_chat_history(history)
        assert "omitted" in result
        # Oldest should be gone
        assert "Q0:" not in result
        # Newest should still be there
        assert "Q299:" in result
        assert "A299:" in result

    def test_truncated_history_within_token_budget(self):
        history = []
        for i in range(300):
            history.extend([
                _make_msg("user", f"Q{i}: " + "word " * 50),
                _make_msg("assistant", f"A{i}: " + "word " * 80),
            ])

        result = _format_chat_history(history)
        result_tokens = _count_tokens(result)
        # Should be within budget (with some slack for the prefix)
        assert result_tokens <= _MAX_CHAT_HISTORY_TOKENS + 100

    def test_exactly_at_budget_not_truncated(self):
        # Build history that's just under budget — should not trigger truncation
        history = []
        for i in range(10):
            history.extend(_make_exchange(i + 1))
        result = _format_chat_history(history)
        assert "omitted" not in result
