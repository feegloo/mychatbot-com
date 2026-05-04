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

from .action_content_types import ACTION_CONTENT_TYPES_EN, ACTION_CONTENT_TYPES_PL
from .emoji_and_dash import EMOJI_AND_DASH_RULES
from .labels_actions import LABELS_ACTIONS_RULES, QUIZ_ACTIONS_RULES
from .professor import PROFESSOR_PROMPT
from .quiz import QUIZ_PROMPT
from .response_formats import RESPONSE_FORMATS_RULES
from .voice_tone import VOICE_TONE_RULES
from .welcome import (
    WELCOME_QUESTIONS_RULES_EN,
    WELCOME_QUESTIONS_RULES_PL,
    WELCOME_SYSTEM_EN,
    WELCOME_SYSTEM_PL,
)

__all__ = [
    "ACTION_CONTENT_TYPES_EN",
    "ACTION_CONTENT_TYPES_PL",
    "EMOJI_AND_DASH_RULES",
    "LABELS_ACTIONS_RULES",
    "PROFESSOR_PROMPT",
    "QUIZ_ACTIONS_RULES",
    "QUIZ_PROMPT",
    "RESPONSE_FORMATS_RULES",
    "VOICE_TONE_RULES",
    "WELCOME_QUESTIONS_RULES_EN",
    "WELCOME_QUESTIONS_RULES_PL",
    "WELCOME_SYSTEM_EN",
    "WELCOME_SYSTEM_PL",
]
