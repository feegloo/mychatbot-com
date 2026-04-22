"""Persistence helpers for the `pdf_pages` table.

This table stores per-page extraction/OCR results for indexed PDFs so that:
  • incremental Chroma upserts during indexing survive container restarts,
  • the welcome message can be regenerated from the full book text once all
    pages have been parsed, and
  • expensive OCR calls (OpenAI Vision) are never repeated for pages we have
    already processed.

Kept minimal on purpose: one module, three functions, no ORM.
"""

from __future__ import annotations

import logging
from typing import Literal

import psycopg2
import psycopg2.extras

from .telemetry import _get_db_pool  # reuse the existing connection pool

logger = logging.getLogger(__name__)

PageSource = Literal["raw", "ocr", "failed"]


def save_page(
    conversation_id: str,
    file_name: str,
    page_nr: int,
    text: str,
    source: PageSource,
    *,
    chapter_nr: int | None = None,
    error_message: str | None = None,
) -> None:
    """Upsert a single parsed page.

    Safe to call repeatedly for the same page — `ON CONFLICT` overwrites the
    previous row so a retry of a failed page replaces the old failure marker.
    """
    try:
        pool = _get_db_pool()
    except Exception as e:
        logger.warning(f"⚠️ pdf_pages save skipped (no DB pool): {e}")
        return

    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pdf_pages
                  (conversation_id, file_name, page_nr, chapter_nr, text, source, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (conversation_id, file_name, page_nr) DO UPDATE SET
                  text = EXCLUDED.text,
                  source = EXCLUDED.source,
                  chapter_nr = EXCLUDED.chapter_nr,
                  error_message = EXCLUDED.error_message,
                  created_at = NOW()
                """,
                (
                    conversation_id,
                    file_name,
                    page_nr,
                    chapter_nr,
                    text or "",
                    source,
                    error_message,
                ),
            )
            conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        logger.warning(f"⚠️ pdf_pages save failed for {file_name} p.{page_nr}: {e}")
    finally:
        pool.putconn(conn)


def get_pages_for_file(conversation_id: str, file_name: str) -> list[dict]:
    """Return all persisted pages for a file, ordered by page number."""
    try:
        pool = _get_db_pool()
    except Exception:
        return []

    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT page_nr, chapter_nr, text, source
                FROM pdf_pages
                WHERE conversation_id = %s AND file_name = %s
                ORDER BY page_nr ASC
                """,
                (conversation_id, file_name),
            )
            return [dict(row) for row in cur.fetchall()]
    except psycopg2.Error as e:
        logger.warning(f"⚠️ pdf_pages read failed for {file_name}: {e}")
        return []
    finally:
        pool.putconn(conn)


def count_pages_for_file(conversation_id: str, file_name: str) -> int:
    """Return the number of pages already persisted for a file."""
    try:
        pool = _get_db_pool()
    except Exception:
        return 0

    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM pdf_pages WHERE conversation_id = %s AND file_name = %s",
                (conversation_id, file_name),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    except psycopg2.Error:
        return 0
    finally:
        pool.putconn(conn)
