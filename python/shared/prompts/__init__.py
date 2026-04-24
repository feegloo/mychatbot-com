"""Centralized system prompts for the RAG engine.

This package is the foundation for step 2 of the prompts refactor: extracting
all welcome-message, assistant-answer, quiz, and action/label rules out of
``rag.py``, ``suggested_questions.py`` and ``describe.py`` and rebuilding them
from a small set of shared building blocks.

Target structure (see PROMPTS_REFACTOR.md):

    prompts/
      __init__.py                 ← public API (this file)
      voice_tone.py               ← shared voice & identity
      response_formats.py         ← rich formatting rules (poems, colors, citations …)
      labels_actions.py           ← ONE source of truth for [action:...] buttons
                                    (reused by welcome + assistant + quiz)
      welcome.py                  ← standard welcome system prompt
      welcome_empty_book.py       ← edge case: scanned PDF, OCR in progress
      assistant.py                ← standard RAG assistant answer prompt
      quiz.py                     ← quiz prompt (moved from rag.py unchanged)

As each module below is populated, it is re-exported here so callers can
``from shared.prompts import …`` without reaching into the old inline locations.
"""

from __future__ import annotations

from .quiz import QUIZ_PROMPT

__all__ = ["QUIZ_PROMPT"]
