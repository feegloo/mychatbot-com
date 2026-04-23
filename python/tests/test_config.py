import os
from unittest.mock import patch

from shared.config import get_settings


class TestGetSettings:
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = get_settings()
            assert settings.chroma_mode == "local"
            assert settings.openai_embedding_model == "text-embedding-3-small"

    def test_custom_models(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_CHAT_MODEL": "gpt-4",
            },
            clear=True,
        ):
            settings = get_settings()
            assert settings.openai_chat_model == "gpt-4"

