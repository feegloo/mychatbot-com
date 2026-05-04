"""Tests for the professor mode prompt (shared.prompts.professor).

Covers:
- PROFESSOR_PROMPT is a valid ChatPromptTemplate
- System prompt contains required structural keywords
- 🤓 emoji trigger is documented in emoji_and_dash
- action_content_types references math/equations content type
- __init__.py exports PROFESSOR_PROMPT
"""

from __future__ import annotations

import re

from langchain_core.prompts import ChatPromptTemplate

from shared.prompts import PROFESSOR_PROMPT
from shared.prompts.action_content_types import ACTION_CONTENT_TYPES_EN, ACTION_CONTENT_TYPES_PL
from shared.prompts.emoji_and_dash import EMOJI_AND_DASH_RULES
from shared.prompts.professor import PROFESSOR_PROMPT as PROFESSOR_PROMPT_DIRECT


class TestProfessorPromptStructure:
    def test_is_chat_prompt_template(self):
        assert isinstance(PROFESSOR_PROMPT, ChatPromptTemplate)

    def test_exported_from_init_matches_direct_import(self):
        assert PROFESSOR_PROMPT is PROFESSOR_PROMPT_DIRECT

    def test_has_two_messages_system_and_human(self):
        assert len(PROFESSOR_PROMPT.messages) == 2

    def test_system_message_is_first(self):
        # First message should have "system" type or similar
        first_msg = PROFESSOR_PROMPT.messages[0]
        msg_type = getattr(first_msg, "role", None) or getattr(
            first_msg, "type", None
        ) or str(type(first_msg).__name__).lower()
        assert "system" in msg_type.lower()

    def _get_system_text(self) -> str:
        system_msg = PROFESSOR_PROMPT.messages[0]
        return system_msg.prompt.template if hasattr(system_msg, "prompt") else str(system_msg)

    def _get_human_text(self) -> str:
        human_msg = PROFESSOR_PROMPT.messages[1]
        return human_msg.prompt.template if hasattr(human_msg, "prompt") else str(human_msg)

    def test_system_adopts_professor_role(self):
        system_text = self._get_system_text()
        assert "professor" in system_text.lower() or "tutor" in system_text.lower()

    def test_system_requires_solution_grading(self):
        system_text = self._get_system_text()
        assert "✅" in system_text
        assert "❌" in system_text

    def test_system_uses_color_markers_for_verdicts(self):
        system_text = self._get_system_text()
        assert "[c:green]" in system_text
        assert "[c:red]" in system_text

    def test_system_includes_latex_instruction(self):
        system_text = self._get_system_text()
        # Should instruct to use LaTeX for math
        assert "$" in system_text or "LaTeX" in system_text or "KaTeX" in system_text

    def test_system_includes_unit_error_example(self):
        system_text = self._get_system_text()
        # kV vs V is the canonical unit error example from the problem statement
        assert "kV" in system_text or "unit" in system_text.lower()

    def test_system_includes_action_buttons(self):
        system_text = self._get_system_text()
        assert "[action:" in system_text

    def test_system_includes_language_instruction(self):
        system_text = self._get_system_text()
        assert "{conversation_language_name}" in system_text

    def test_human_template_has_required_variables(self):
        human_text = self._get_human_text()
        required_vars = [
            "{context}",
            "{welcome_messages}",
            "{chat_history}",
            "{question}",
            "{conversation_name}",
            "{conversation_id}",
            "{matched_pages}",
            "{exif_metadata}",
        ]
        for var in required_vars:
            assert var in human_text, f"Missing variable {var} in human template"

    def test_system_requires_ocr_of_problems(self):
        system_text = self._get_system_text()
        assert "OCR" in system_text or "transcribe" in system_text.lower() or "Transcribe" in system_text

    def test_system_requires_summary_table(self):
        system_text = self._get_system_text()
        assert "Summary" in system_text or "summary" in system_text

    def test_system_requires_per_problem_structure(self):
        system_text = self._get_system_text()
        # Should mention "Problem N" or per-problem structure
        assert "Problem" in system_text

    def test_system_mentions_7_action_buttons(self):
        system_text = self._get_system_text()
        assert "7" in system_text and "[action:" in system_text


class TestProfessorEmojiReservation:
    def test_nerd_emoji_reserved_in_emoji_and_dash(self):
        assert "🤓" in EMOJI_AND_DASH_RULES

    def test_nerd_emoji_described_as_reserved(self):
        assert "RESERVED" in EMOJI_AND_DASH_RULES
        # The text near 🤓 should describe it as triggering professor mode
        idx = EMOJI_AND_DASH_RULES.find("🤓")
        context = EMOJI_AND_DASH_RULES[max(0, idx - 200):idx + 200]
        assert "professor" in context.lower() or "tutor" in context.lower() or "exercise" in context.lower()

    def test_nerd_emoji_not_used_as_general_emoji(self):
        # The rules must say NOT to use 🤓 as a general emoji
        assert "Never use 🤓" in EMOJI_AND_DASH_RULES or "never use 🤓" in EMOJI_AND_DASH_RULES.lower() or (
            "🤓" in EMOJI_AND_DASH_RULES and "RESERVED EXCLUSIVELY" in EMOJI_AND_DASH_RULES
        )


class TestMathContentType:
    def test_math_equations_content_type_in_en(self):
        # Must include math/equations/exercises content type
        text = ACTION_CONTENT_TYPES_EN.lower()
        assert "math" in text or "equation" in text or "exercise" in text or "academic" in text

    def test_math_equations_content_type_in_pl(self):
        text = ACTION_CONTENT_TYPES_PL.lower()
        assert "mat" in text or "równ" in text or "ćwicz" in text or "zadani" in text

    def test_nerd_emoji_in_math_content_type_en(self):
        assert "🤓" in ACTION_CONTENT_TYPES_EN

    def test_nerd_emoji_in_math_content_type_pl(self):
        assert "🤓" in ACTION_CONTENT_TYPES_PL

    def test_position_3_mandatory_for_math_en(self):
        # Should specify position 3 as the mandatory professor action slot
        text = ACTION_CONTENT_TYPES_EN
        assert "position 3" in text.lower() or "POSITION 3" in text or "3rd" in text.lower()

    def test_verify_exercise_solutions_label_en(self):
        assert "Verify exercise solutions" in ACTION_CONTENT_TYPES_EN or "Solve equations" in ACTION_CONTENT_TYPES_EN

    def test_verify_exercise_solutions_label_pl(self):
        assert "Sprawdź" in ACTION_CONTENT_TYPES_PL or "Rozwiąż" in ACTION_CONTENT_TYPES_PL

    def test_no_fiction_for_math_en(self):
        # Must prohibit fiction/creative actions for math content
        text = ACTION_CONTENT_TYPES_EN
        # Find the math/exercises section (starts before 🤓)
        idx = text.find("MATH / PHYSICS / ECONOMICS")
        assert idx != -1, "Math/exercises section not found in EN content types"
        # Look at a broader window that includes the full section
        section = text[idx:idx + 1500]
        assert "PROHIBITED" in section or "prohibited" in section.lower() or "fairy tale" in section.lower() or "fairy tales" in section.lower()


class TestWelcomeProfessorRole:
    """Verify the welcome prompt registers math/exercises → professor role."""

    def _get_welcome_text(self) -> str:
        from shared.prompts.welcome import WELCOME_SYSTEM_EN
        return WELCOME_SYSTEM_EN

    def test_professor_role_listed_in_welcome_en(self):
        text = self._get_welcome_text()
        assert "professor" in text.lower() or "tutor" in text.lower()

    def test_math_physics_context_in_welcome_en(self):
        text = self._get_welcome_text()
        assert "math" in text.lower() or "equation" in text.lower() or "exercise" in text.lower()

    def test_solution_verification_in_welcome_en(self):
        text = self._get_welcome_text()
        # Should instruct to give a preliminary verdict in welcome
        assert "correct" in text.lower() and ("✅" in text or "❌" in text)
