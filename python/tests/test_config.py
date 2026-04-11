import pytest
import os
from unittest.mock import patch
from shared.config import get_settings


class TestGetSettings:
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = get_settings()
            assert settings.chroma_mode == "local"
            assert settings.openai_embedding_model == "text-embedding-3-small"

    def test_auto_fallback_to_openai(self):
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "sk-test-key",
        }, clear=True):
            settings = get_settings()
            assert settings.llm_provider == "openai"
            assert settings.openai_api_key == "sk-test-key"

    def test_respects_anthropic_when_key_present(self):
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENAI_API_KEY": "sk-test",
        }, clear=True):
            settings = get_settings()
            assert settings.llm_provider == "anthropic"

    def test_custom_models(self):
        with patch.dict(os.environ, {
            "OPENAI_CHAT_MODEL": "gpt-4",
            "ANTHROPIC_CHAT_MODEL": "claude-3-opus",
        }, clear=True):
            settings = get_settings()
            assert settings.openai_chat_model == "gpt-4"
            assert settings.anthropic_chat_model == "claude-3-opus"
