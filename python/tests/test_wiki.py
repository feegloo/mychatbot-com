"""Unit tests for wiki.py — no LLM, no Chroma, no network I/O.

Covers:
  - _cosine_similarity                 — math correctness
  - _build_chunk_correlation_block     — embedding fetch, pair filtering, output format
  - _build_raw_material                — integration of correlation block into sections
  - build_conversation_wiki            — end-to-end with mocked LLM chain
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

from shared.wiki import (
    _build_chunk_correlation_block,
    _build_raw_material,
    _cosine_similarity,
    build_conversation_wiki,
)

# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_unit_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_non_unit_vectors_normalised(self):
        # magnitude should not matter — [2,0] ⊥ [0,3]
        assert _cosine_similarity([2.0, 0.0], [0.0, 3.0]) == pytest.approx(0.0)

    def test_zero_vector_returns_zero(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_known_45_degree_angle(self):
        s = 1.0 / math.sqrt(2)
        assert _cosine_similarity([1.0, 0.0], [s, s]) == pytest.approx(s, abs=1e-9)

    def test_symmetry(self):
        a = [0.6, 0.8]
        b = [0.8, 0.6]
        assert _cosine_similarity(a, b) == pytest.approx(_cosine_similarity(b, a))

    def test_partial_overlap(self):
        # Both vectors share first component — expect positive similarity
        score = _cosine_similarity([1.0, 1.0], [1.0, 0.0])
        assert 0.0 < score < 1.0

    def test_negative_similarity(self):
        # Mostly opposed directions
        score = _cosine_similarity([1.0, 0.1], [-1.0, 0.1])
        assert score < 0.0


# ---------------------------------------------------------------------------
# _build_chunk_correlation_block
# ---------------------------------------------------------------------------


def _make_chroma_collection(chunk_ids: list[str], embeddings: list[list[float]]):
    """Return a mock Chroma collection whose .get() returns the given data."""
    col = MagicMock()
    col.get.return_value = {
        "ids": chunk_ids,
        "embeddings": embeddings,
    }
    return col


class TestBuildChunkCorrelationBlock:
    def _patch_client(self, collection):
        client = MagicMock()
        client.get_or_create_collection.return_value = collection
        return patch("shared.vector_store.get_client", return_value=client)

    def test_identical_embeddings_score_one(self):
        emb = [1.0, 0.0]
        col = _make_chroma_collection(["c1", "c2"], [emb, emb])
        with self._patch_client(col):
            result = _build_chunk_correlation_block("col", ["c1", "c2"], ["Match 1", "Match 2"])
        assert "Match 1 <-> Match 2: +1.00" in result

    def test_orthogonal_embeddings_filtered_out(self):
        # score = 0.0 is below the |0.10| threshold → pair excluded
        col = _make_chroma_collection(
            ["c1", "c2"],
            [[1.0, 0.0], [0.0, 1.0]],
        )
        with self._patch_client(col):
            result = _build_chunk_correlation_block("col", ["c1", "c2"], ["Match 1", "Match 2"])
        # Below threshold → no pairs → empty string
        assert result == ""

    def test_negative_correlation_included(self):
        col = _make_chroma_collection(
            ["c1", "c2"],
            [[1.0, 0.0], [-1.0, 0.0]],
        )
        with self._patch_client(col):
            result = _build_chunk_correlation_block("col", ["c1", "c2"], ["Match 1", "Match 2"])
        assert "Match 1 <-> Match 2: -1.00" in result

    def test_header_and_legend_present(self):
        emb = [1.0, 0.0]
        col = _make_chroma_collection(["c1", "c2"], [emb, emb])
        with self._patch_client(col):
            result = _build_chunk_correlation_block("col", ["c1", "c2"], ["A", "B"])
        assert "CHUNK PAIRWISE COSINE CORRELATION" in result
        assert "1.0 = closely related" in result
        assert "-1.0 = contrasting" in result

    def test_pairs_sorted_strongest_first(self):
        # Three chunks: c1↔c2 strong, c1↔c3 weak, c2↔c3 moderate
        e1 = [1.0, 0.0, 0.0]
        e2 = [0.9, 0.436, 0.0]   # cosine with e1 ≈ 0.90
        e3 = [0.5, 0.5, 0.707]   # cosine with e1 ≈ 0.50, with e2 ≈ smaller
        col = _make_chroma_collection(["c1", "c2", "c3"], [e1, e2, e3])
        with self._patch_client(col):
            result = _build_chunk_correlation_block(
                "col", ["c1", "c2", "c3"], ["M1", "M2", "M3"]
            )
        lines = [line for line in result.splitlines() if "<->" in line]
        # First listed pair should have the highest |score|
        scores = [float(line.split(": ")[1]) for line in lines]
        assert scores == sorted(scores, key=abs, reverse=True)

    def test_single_chunk_returns_empty(self):
        col = _make_chroma_collection(["c1"], [[1.0, 0.0]])
        with self._patch_client(col):
            result = _build_chunk_correlation_block("col", ["c1"], ["Match 1"])
        assert result == ""

    def test_chroma_exception_returns_empty(self):
        client = MagicMock()
        client.get_or_create_collection.side_effect = RuntimeError("DB unavailable")
        with patch("shared.vector_store.get_client", return_value=client):
            # Should not raise — failures are silently swallowed
            result = _build_chunk_correlation_block("col", ["c1", "c2"], ["A", "B"])
        assert result == ""

    def test_missing_embedding_for_id_skipped(self):
        # Chroma returns only c1 (c2 missing)
        col = _make_chroma_collection(["c1"], [[1.0, 0.0]])
        with self._patch_client(col):
            result = _build_chunk_correlation_block("col", ["c1", "c2"], ["A", "B"])
        # Only one embedding resolved → no pairs possible
        assert result == ""


# ---------------------------------------------------------------------------
# _build_raw_material — correlation block is appended when chunks are present
# ---------------------------------------------------------------------------


def _make_rows(n: int = 3) -> list[dict]:
    return [
        {
            "chunk_id": f"c{i}",
            "text": f"Chunk text {i}",
            "file_name": "doc.pdf",
            "page": i,
            "chapter_number": None,
            "chapter_name": None,
            "distance": 0.3,
            "metadata": {},
        }
        for i in range(1, n + 1)
    ]


class TestBuildRawMaterial:
    def _patch_deps(self, rows, corr_block="== CHUNK PAIRWISE COSINE CORRELATION ==\nA <-> B: +0.80"):
        """Patch all external dependencies used by _build_raw_material."""
        patches = [
            patch("shared.vector_store.query_chunks", return_value=rows),
            patch("shared.rag._extract_matched_pages", return_value="page text"),
            patch("shared.rag._extract_chapter_context", return_value="chapter text"),
            patch("shared.wiki._build_chunk_correlation_block", return_value=corr_block),
        ]
        return patches

    def test_correlation_block_appended_to_sections(self):
        rows = _make_rows(3)
        patches = self._patch_deps(rows)
        for p in patches:
            p.start()
        try:
            material, count = _build_raw_material(
                collection_name="col",
                conversation_id="conv1",
                welcome_message="Welcome text about the document.",
                storage_dir="/fake/dir",
                char_budget=500_000,
            )
        finally:
            for p in patches:
                p.stop()

        assert "CHUNK PAIRWISE COSINE CORRELATION" in material
        assert count == 3

    def test_empty_corr_block_not_appended(self):
        rows = _make_rows(2)
        patches = self._patch_deps(rows, corr_block="")
        for p in patches:
            p.start()
        try:
            material, _ = _build_raw_material(
                collection_name="col",
                conversation_id="conv1",
                welcome_message="Welcome text.",
                storage_dir="/fake/dir",
                char_budget=500_000,
            )
        finally:
            for p in patches:
                p.stop()

        assert "CHUNK PAIRWISE COSINE CORRELATION" not in material

    def test_no_rows_returns_placeholder(self):
        with patch("shared.vector_store.query_chunks", return_value=[]):
            material, count = _build_raw_material(
                collection_name="col",
                conversation_id="conv1",
                welcome_message="Welcome.",
                storage_dir=None,
                char_budget=500_000,
            )
        assert count == 0
        assert "no matched material" in material

    def test_material_trimmed_to_char_budget(self):
        rows = _make_rows(5)
        patches = self._patch_deps(rows)
        for p in patches:
            p.start()
        try:
            material, _ = _build_raw_material(
                collection_name="col",
                conversation_id="conv1",
                welcome_message="Welcome.",
                storage_dir="/fake/dir",
                char_budget=50,  # very tight budget
            )
        finally:
            for p in patches:
                p.stop()

        assert "trimmed" in material

    def test_chunk_labels_match_ids_in_section(self):
        rows = _make_rows(2)
        with (
            patch("shared.vector_store.query_chunks", return_value=rows),
            patch("shared.rag._extract_matched_pages", return_value=""),
            patch("shared.rag._extract_chapter_context", return_value=""),
            patch("shared.wiki._build_chunk_correlation_block") as mock_corr,
        ):
            mock_corr.return_value = ""
            _build_raw_material(
                collection_name="col",
                conversation_id="conv1",
                welcome_message="Welcome.",
                storage_dir=None,
                char_budget=500_000,
            )
            # Verify correlation block received the correct chunk IDs and labels
            call_args = mock_corr.call_args
            ids_arg = call_args[0][1]
            labels_arg = call_args[0][2]
            assert ids_arg == ["c1", "c2"]
            assert labels_arg == ["Match 1", "Match 2"]


# ---------------------------------------------------------------------------
# build_conversation_wiki — end-to-end with mocked chain
# ---------------------------------------------------------------------------


class TestBuildConversationWiki:
    _WIKI_OUTPUT = "# Test Doc — Internal Wiki\n\n## Domain\nTest domain."

    def _patch_all(self, wiki_text=_WIKI_OUTPUT, chunk_count=3):
        raw_material = "== TOP MATCHES ==\nchunk text\n\n== CHUNK PAIRWISE COSINE CORRELATION ==\nA <-> B: +0.75"
        return [
            patch(
                "shared.wiki._build_raw_material",
                return_value=(raw_material, chunk_count),
            ),
            patch("shared.rag.get_llm", return_value=MagicMock()),
            patch(
                "shared.wiki.traced_llm_call",
                return_value=(wiki_text, {}),
            ),
            patch("shared.wiki.detect_language", return_value="en"),
        ]

    def test_returns_wiki_text_on_success(self):
        patches = self._patch_all()
        for p in patches:
            p.start()
        try:
            result = build_conversation_wiki(
                conversation_id="conv1",
                collection_name="col",
                conversation_title="Test Doc",
                welcome_message="This document is about testing.",
                storage_dir="/fake/dir",
            )
        finally:
            for p in patches:
                p.stop()

        assert result == self._WIKI_OUTPUT

    def test_returns_none_for_empty_welcome(self):
        result = build_conversation_wiki(
            conversation_id="conv1",
            collection_name="col",
            conversation_title="Test",
            welcome_message="",
            storage_dir=None,
        )
        assert result is None

    def test_returns_none_when_no_chunks(self):
        patches = self._patch_all(chunk_count=0)
        for p in patches:
            p.start()
        try:
            result = build_conversation_wiki(
                conversation_id="conv1",
                collection_name="col",
                conversation_title="Test",
                welcome_message="Welcome text.",
                storage_dir=None,
            )
        finally:
            for p in patches:
                p.stop()

        assert result is None

    def test_strips_code_fence_if_model_adds_it(self):
        fenced = "```markdown\n# Title\n\n## Domain\nStuff.\n```"
        patches = self._patch_all(wiki_text=fenced)
        for p in patches:
            p.start()
        try:
            result = build_conversation_wiki(
                conversation_id="conv1",
                collection_name="col",
                conversation_title="Test",
                welcome_message="Welcome.",
                storage_dir=None,
            )
        finally:
            for p in patches:
                p.stop()

        assert result is not None
        assert not result.startswith("```")
        assert "# Title" in result

    def test_returns_none_on_llm_failure(self):
        with (
            patch("shared.wiki._build_raw_material", return_value=("material", 3)),
            patch("shared.rag.get_llm", return_value=MagicMock()),
            patch("shared.wiki.traced_llm_call", side_effect=RuntimeError("LLM down")),
            patch("shared.wiki.detect_language", return_value="en"),
        ):
            result = build_conversation_wiki(
                conversation_id="conv1",
                collection_name="col",
                conversation_title="Test",
                welcome_message="Welcome.",
                storage_dir=None,
            )
        assert result is None

    def test_trims_oversized_output(self):
        long_wiki = "x" * 25_000  # exceeds _MAX_OUTPUT_CHARS = 16_000
        patches = self._patch_all(wiki_text=long_wiki)
        for p in patches:
            p.start()
        try:
            result = build_conversation_wiki(
                conversation_id="conv1",
                collection_name="col",
                conversation_title="Test",
                welcome_message="Welcome.",
                storage_dir=None,
            )
        finally:
            for p in patches:
                p.stop()

        assert result is not None
        assert len(result) <= 16_000 + len("\n\n_(trimmed)_")
        assert result.endswith("_(trimmed)_")

    def test_returns_none_for_empty_llm_output(self):
        patches = self._patch_all(wiki_text="")
        for p in patches:
            p.start()
        try:
            result = build_conversation_wiki(
                conversation_id="conv1",
                collection_name="col",
                conversation_title="Test",
                welcome_message="Welcome.",
                storage_dir=None,
            )
        finally:
            for p in patches:
                p.stop()

        assert result is None
