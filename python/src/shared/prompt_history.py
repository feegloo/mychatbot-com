"""Prompt history: log full LLM prompts and responses to PostgreSQL.

Writes to the `prompt_history` table with prompt text, response text,
token usage, timing, and operation labels for later analysis.
"""

from __future__ import annotations

import logging
import uuid

from .telemetry import _get_db_pool, _utc_now

logger = logging.getLogger(__name__)


def log_prompt(
    *,
    conversation_id: str | None,
    operation: str,
    model: str,
    prompt_text: str,
    response_text: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    cached_tokens: int | None = None,
    duration_ms: int | None = None,
) -> str | None:
    """Insert a row into prompt_history. Returns the row ID or None on failure."""
    try:
        pool = _get_db_pool()
        conn = pool.getconn()
        try:
            row_id = str(uuid.uuid4())
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO prompt_history
                       (id, conversation_id, operation, model,
                        prompt_text, response_text,
                        prompt_tokens, completion_tokens, total_tokens, cached_tokens,
                        duration_ms, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        row_id,
                        conversation_id,
                        operation,
                        model,
                        prompt_text,
                        response_text,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                        cached_tokens or 0,
                        duration_ms,
                        _utc_now(),
                    ),
                )
            conn.commit()
            logger.debug(
                f"[PROMPT_HISTORY] logged {operation} | model={model} "
                f"prompt={len(prompt_text)} chars | response={len(response_text or '')} chars"
            )
            return row_id
        finally:
            pool.putconn(conn)
    except Exception as e:
        logger.warning(f"[PROMPT_HISTORY] DB write failed (non-fatal): {e}")
        return None
