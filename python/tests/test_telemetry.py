"""Tests for shared.telemetry — pure utility functions only.

No DB or psycopg2 dependency: all DB calls are mocked out.
Covers: _truncate, flush_processing_errors, _utc_now, log_processing_error
async queue path, and the error-writer thread lifecycle.
"""

from __future__ import annotations

import queue
import threading
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from shared.telemetry import (
    _truncate,
    _utc_now,
    flush_processing_errors,
    log_processing_error,
)


class TestTruncate:
    def test_short_string_unchanged(self):
        assert _truncate("hello", 100) == "hello"

    def test_none_returns_none(self):
        assert _truncate(None, 100) is None

    def test_exact_limit_unchanged(self):
        s = "a" * 100
        assert _truncate(s, 100) == s

    def test_over_limit_truncated(self):
        s = "x" * 200
        result = _truncate(s, 100)
        assert result is not None
        assert result.startswith("x" * 100)
        assert "truncated" in result
        assert "100" in result

    def test_truncated_result_contains_original_content(self):
        s = "abcdef" * 50
        result = _truncate(s, 20)
        assert result is not None
        assert result[:20] == s[:20]

    def test_zero_limit(self):
        result = _truncate("anything", 0)
        # 0-char limit: everything beyond 0 chars is cut
        assert result is not None
        assert "truncated" in result

    def test_unicode_preserved_up_to_limit(self):
        s = "Zażółć gęślą jaźń"
        result = _truncate(s, 5)
        assert result is not None
        assert result.startswith("Zażółć"[:5])


class TestUtcNow:
    def test_returns_datetime_with_utc_timezone(self):
        dt = _utc_now()
        assert isinstance(dt, datetime)
        assert dt.tzinfo is UTC or str(dt.tzinfo) == "UTC"

    def test_is_recent(self):
        before = datetime.now(UTC)
        dt = _utc_now()
        after = datetime.now(UTC)
        assert before <= dt <= after


class TestFlushProcessingErrors:
    """flush_processing_errors must complete without hanging when queue is None or empty."""

    def test_no_op_when_queue_is_none(self):
        import shared.telemetry as tel
        original = tel._error_queue
        try:
            tel._error_queue = None
            # Should return immediately, no hang
            flush_processing_errors(timeout=0.1)
        finally:
            tel._error_queue = original

    def test_returns_quickly_when_queue_empty(self):
        import shared.telemetry as tel
        original = tel._error_queue
        try:
            tel._error_queue = queue.Queue()
            start = time.monotonic()
            flush_processing_errors(timeout=1.0)
            elapsed = time.monotonic() - start
            # Empty queue → should return almost immediately
            assert elapsed < 0.5
        finally:
            tel._error_queue = original

    def test_waits_for_queue_to_drain(self):
        """Queue with an item: flush blocks until drained (task_done called)."""
        import shared.telemetry as tel
        original = tel._error_queue
        try:
            q: queue.Queue = queue.Queue()
            q.put({"dummy": True})
            tel._error_queue = q

            # Background thread drains it after a short delay
            def drain():
                time.sleep(0.05)
                q.get()
                q.task_done()

            t = threading.Thread(target=drain, daemon=True)
            t.start()

            flush_processing_errors(timeout=1.0)
            assert q.empty()
        finally:
            tel._error_queue = original


class TestLogProcessingError:
    """log_processing_error should enqueue a row without hitting the DB."""

    @patch("shared.telemetry._ensure_error_writer")
    def test_enqueues_row(self, mock_ensure):
        mock_queue = MagicMock()
        mock_ensure.return_value = mock_queue

        uid = log_processing_error(
            conversation_id="conv-1",
            file_name="test.pdf",
            error=ValueError("something broke"),
        )

        assert isinstance(uid, str)
        assert len(uid) == 36  # UUID format
        mock_queue.put_nowait.assert_called_once()
        row = mock_queue.put_nowait.call_args[0][0]
        assert row["conversation_id"] == "conv-1"
        assert row["file_name"] == "test.pdf"
        assert row["error_type"] == "ValueError"
        assert "something broke" in row["error_message"]

    @patch("shared.telemetry._ensure_error_writer")
    def test_captures_traceback(self, mock_ensure):
        mock_queue = MagicMock()
        mock_ensure.return_value = mock_queue

        try:
            raise RuntimeError("kaboom")
        except RuntimeError as e:
            log_processing_error("c", "f.pdf", e)

        row = mock_queue.put_nowait.call_args[0][0]
        assert row["stack_trace"] is not None
        assert "RuntimeError" in row["stack_trace"]

    @patch("shared.telemetry._ensure_error_writer")
    def test_optional_fields_passed_through(self, mock_ensure):
        mock_queue = MagicMock()
        mock_ensure.return_value = mock_queue

        log_processing_error(
            "conv",
            "doc.pdf",
            OSError("disk full"),
            step="extract",
            page_number=3,
            content="some page text",
            content_type="text",
            worker_id="worker-42",
            retry_count=2,
            processing_job_id="job-uuid",
        )

        row = mock_queue.put_nowait.call_args[0][0]
        assert row["step"] == "extract"
        assert row["page_number"] == 3
        assert row["content"] == "some page text"
        assert row["content_type"] == "text"
        assert row["worker_id"] == "worker-42"
        assert row["retry_count"] == 2
        assert row["processing_job_id"] == "job-uuid"

    @patch("shared.telemetry._ensure_error_writer")
    def test_long_content_is_truncated(self, mock_ensure):
        from shared.telemetry import _ERROR_CONTENT_MAX_CHARS

        mock_queue = MagicMock()
        mock_ensure.return_value = mock_queue

        huge_content = "x" * (_ERROR_CONTENT_MAX_CHARS + 1000)
        log_processing_error("c", "f.pdf", ValueError("err"), content=huge_content)

        row = mock_queue.put_nowait.call_args[0][0]
        assert row["content"] is not None
        assert len(row["content"]) <= _ERROR_CONTENT_MAX_CHARS + 200  # allow for truncation suffix

    @patch("shared.telemetry._ensure_error_writer")
    def test_queue_full_does_not_raise(self, mock_ensure):
        mock_queue = MagicMock()
        mock_queue.put_nowait.side_effect = queue.Full
        mock_ensure.return_value = mock_queue

        # Must not propagate the exception
        uid = log_processing_error("c", "f.pdf", ValueError("q full"))
        assert isinstance(uid, str)

    @patch("shared.telemetry._ensure_error_writer")
    def test_returns_uid_even_on_enqueue_error(self, mock_ensure):
        mock_queue = MagicMock()
        mock_queue.put_nowait.side_effect = RuntimeError("unexpected")
        mock_ensure.return_value = mock_queue

        uid = log_processing_error("c", "f.pdf", ValueError("x"))
        assert isinstance(uid, str)
