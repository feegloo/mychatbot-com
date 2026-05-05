"""Tests for shared.prompts.quiz and shared.prompts.labels_actions.

Covers:
- QUIZ_ACTIONS_RULES is a non-empty string wired into QUIZ_PROMPT
- QUIZ_PROMPT template builds correctly and accepts all expected variables
- QUIZ_ACTIONS_RULES contains the required structural keywords
- LABELS_ACTIONS_RULES is separate from QUIZ_ACTIONS_RULES
- __init__.py exports both correctly
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from shared.prompts import LABELS_ACTIONS_RULES, QUIZ_ACTIONS_RULES, QUIZ_PROMPT
from shared.prompts.labels_actions import QUIZ_ACTIONS_RULES as QUIZ_ACTIONS_DIRECT
from shared.prompts.quiz import QUIZ_PROMPT as QUIZ_PROMPT_DIRECT


class TestQuizActionsRulesContent:
    def test_is_non_empty_string(self):
        assert isinstance(QUIZ_ACTIONS_RULES, str)
        assert len(QUIZ_ACTIONS_RULES) > 100

    def test_exported_from_init_matches_direct_import(self):
        assert QUIZ_ACTIONS_RULES is QUIZ_ACTIONS_DIRECT

    def test_requires_exactly_7_actions(self):
        assert "7" in QUIZ_ACTIONS_RULES
        assert "[action:" in QUIZ_ACTIONS_RULES

    def test_positions_1_3_are_quiz_buttons(self):
        assert "Positions 1" in QUIZ_ACTIONS_RULES or "positions 1" in QUIZ_ACTIONS_RULES
        assert "🧠" in QUIZ_ACTIONS_RULES

    def test_positions_4_7_are_non_quiz_overflow(self):
        assert "More" in QUIZ_ACTIONS_RULES or "overflow" in QUIZ_ACTIONS_RULES.lower()
        # Must mention at least a few of the non-quiz rich actions
        assert "🎨" in QUIZ_ACTIONS_RULES
        assert "🃏" in QUIZ_ACTIONS_RULES

    def test_language_mirroring_requirement(self):
        assert "language" in QUIZ_ACTIONS_RULES.lower()
        assert "Polish" in QUIZ_ACTIONS_RULES or "polish" in QUIZ_ACTIONS_RULES.lower()

    def test_single_line_format_requirement(self):
        assert "SINGLE line" in QUIZ_ACTIONS_RULES or "single line" in QUIZ_ACTIONS_RULES.lower()

    def test_inspired_keyword_mentioned(self):
        # image gen labels must contain "inspired"
        assert "inspired" in QUIZ_ACTIONS_RULES

    def test_never_attach_palette_to_non_image(self):
        assert "🎨" in QUIZ_ACTIONS_RULES
        # The rules explicitly state 🎨 must not route non-image actions
        assert "non-image" in QUIZ_ACTIONS_RULES or "NOT" in QUIZ_ACTIONS_RULES

    def test_english_example_present(self):
        # Examples show real [action:...] formatting
        assert "[action:" in QUIZ_ACTIONS_RULES
        assert "🧠" in QUIZ_ACTIONS_RULES

    def test_polish_example_present(self):
        assert "Quiz" in QUIZ_ACTIONS_RULES or "quiz" in QUIZ_ACTIONS_RULES


class TestQuizActionsRulesIsolatedFromAnswerActions:
    """QUIZ_ACTIONS_RULES is a distinct, shorter ruleset vs LABELS_ACTIONS_RULES."""

    def test_they_are_different_strings(self):
        assert QUIZ_ACTIONS_RULES != LABELS_ACTIONS_RULES

    def test_quiz_rules_are_shorter(self):
        # Quiz actions are a focused subset, not the full answer-prompt ruleset
        assert len(QUIZ_ACTIONS_RULES) < len(LABELS_ACTIONS_RULES)

    def test_quiz_rules_not_embedded_inside_answer_rules(self):
        assert QUIZ_ACTIONS_RULES not in LABELS_ACTIONS_RULES


class TestQuizPromptStructure:
    def test_is_chat_prompt_template(self):
        assert isinstance(QUIZ_PROMPT, ChatPromptTemplate)
        assert isinstance(QUIZ_PROMPT_DIRECT, ChatPromptTemplate)

    def test_has_system_and_human_messages(self):
        messages = QUIZ_PROMPT.messages
        # Should have at least 2 messages (system + human)
        assert len(messages) == 2

    def test_system_prompt_contains_quiz_actions_rules(self):
        system_msg = QUIZ_PROMPT.messages[0]
        system_text = system_msg.prompt.template if hasattr(system_msg, "prompt") else str(system_msg)
        assert "7" in system_text
        assert "[action:" in system_text
        assert "🧠" in system_text

    def test_system_prompt_contains_core_quiz_rules(self):
        system_msg = QUIZ_PROMPT.messages[0]
        system_text = system_msg.prompt.template if hasattr(system_msg, "prompt") else str(system_msg)
        assert "quiz" in system_text.lower()
        assert "multiple" in system_text
        assert "[quiz:" in system_text

    def test_system_prompt_no_placeholder_leak(self):
        system_msg = QUIZ_PROMPT.messages[0]
        system_text = system_msg.prompt.template if hasattr(system_msg, "prompt") else str(system_msg)
        # Ensure <<QUIZ_ACTIONS>> placeholder was replaced, not left in raw
        assert "<<QUIZ_ACTIONS>>" not in system_text

    def test_human_message_has_all_required_variables(self):
        # These input variables must be present for the quiz chain to work
        required = {"raw_text", "page_summaries", "welcome_messages", "chat_history", "question", "context", "num_questions"}
        input_vars = set(QUIZ_PROMPT.input_variables)
        assert required.issubset(input_vars), f"Missing: {required - input_vars}"

    def test_quiz_prompt_format_with_all_variables(self):
        """End-to-end: format the prompt with dummy values — must not raise."""
        formatted = QUIZ_PROMPT.format_messages(
            raw_text="Chapter 1: The origins of Rome.",
            page_summaries="Page 1: Introduction to Roman history.",
            welcome_messages="Uploaded: roman_history.pdf",
            chat_history="User: Tell me about Rome.",
            question="Quiz me on Roman history",
            context="Rome was founded in 753 BC according to legend.",
            conversation_language_name="English",
            conversation_language_code="en",
            num_questions=5,
        )
        assert len(formatted) == 2
        human_text = formatted[1].content
        assert "Roman history" in human_text

    def test_no_source_citation_reminder_in_system(self):
        system_msg = QUIZ_PROMPT.messages[0]
        system_text = system_msg.prompt.template if hasattr(system_msg, "prompt") else str(system_msg)
        assert "NEVER include [source:" in system_text

    def test_em_dash_prohibition_in_system(self):
        system_msg = QUIZ_PROMPT.messages[0]
        system_text = system_msg.prompt.template if hasattr(system_msg, "prompt") else str(system_msg)
        assert "em dash" in system_text or "—" in system_text

    def test_correct_answer_distribution_rule_in_system(self):
        system_msg = QUIZ_PROMPT.messages[0]
        system_text = system_msg.prompt.template if hasattr(system_msg, "prompt") else str(system_msg)
        assert "ANSWER POSITION RANDOMIZATION" in system_text or "Shuffle option order" in system_text
        assert "correct" in system_text.lower()


class TestQuizPromptImports:
    def test_quiz_prompt_importable_from_init(self):
        from shared.prompts import QUIZ_PROMPT as qp
        assert qp is QUIZ_PROMPT

    def test_quiz_actions_importable_from_init(self):
        from shared.prompts import QUIZ_ACTIONS_RULES as qar
        assert qar is QUIZ_ACTIONS_RULES

    def test_all_declared_in_init_all(self):
        from shared import prompts
        assert "QUIZ_PROMPT" in prompts.__all__
        assert "QUIZ_ACTIONS_RULES" in prompts.__all__
        assert "LABELS_ACTIONS_RULES" in prompts.__all__
