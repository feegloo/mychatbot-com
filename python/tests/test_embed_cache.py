"""Tests for embedding cache in vector_store module."""

from unittest.mock import patch, MagicMock

from shared.vector_store import _embed_single_cached


class TestEmbedSingleCached:
    """Verify that _embed_single_cached uses LRU cache."""

    def setup_method(self):
        _embed_single_cached.cache_clear()

    def test_returns_tuple(self):
        fake_embedding = [0.1, 0.2, 0.3]
        with patch("shared.vector_store.embed_texts", return_value=[fake_embedding]) as mock:
            result = _embed_single_cached("hello world")
            assert isinstance(result, tuple)
            assert list(result) == fake_embedding
            mock.assert_called_once_with(["hello world"])

    def test_caches_repeated_calls(self):
        fake_embedding = [0.1, 0.2, 0.3]
        with patch("shared.vector_store.embed_texts", return_value=[fake_embedding]) as mock:
            result1 = _embed_single_cached("same question")
            result2 = _embed_single_cached("same question")
            assert result1 == result2
            # embed_texts should only be called once due to cache
            mock.assert_called_once()

    def test_different_inputs_not_cached(self):
        with patch("shared.vector_store.embed_texts", side_effect=[[[ 0.1]], [[0.2]]]) as mock:
            _embed_single_cached("question A")
            _embed_single_cached("question B")
            assert mock.call_count == 2

    def test_cache_info(self):
        fake_embedding = [0.1, 0.2, 0.3]
        with patch("shared.vector_store.embed_texts", return_value=[fake_embedding]):
            _embed_single_cached("test")
            _embed_single_cached("test")
            info = _embed_single_cached.cache_info()
            assert info.hits == 1
            assert info.misses == 1
