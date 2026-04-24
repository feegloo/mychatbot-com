"""Unit tests for the hybrid L2 + cosine retrieval in vector_store.py.

These tests are deliberately free of any network / Chroma / OpenAI I/O — all
external calls are replaced with mocks so the suite runs offline and fast.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

import src.shared.vector_store as vs_module
from src.shared.vector_store import (
    HYBRID_COSINE_WEIGHT,
    HYBRID_FETCH_MULTIPLIER,
    HYBRID_L2_WEIGHT,
    _cosine_similarity,
    query_chunks,
)

# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_unit_vectors_returns_one(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_returns_zero(self):
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_returns_minus_one(self):
        assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_non_unit_vectors_are_normalised(self):
        # [2, 0] and [0, 3] are orthogonal regardless of magnitude
        assert _cosine_similarity([2.0, 0.0], [0.0, 3.0]) == pytest.approx(0.0)

    def test_zero_vector_returns_zero(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_known_angle(self):
        # 45-degree angle between [1,0] and [1,1]/sqrt(2)
        s = 1.0 / math.sqrt(2)
        result = _cosine_similarity([1.0, 0.0], [s, s])
        assert result == pytest.approx(s, abs=1e-9)

    def test_symmetry(self):
        a = [0.6, 0.8]
        b = [0.8, 0.6]
        assert _cosine_similarity(a, b) == pytest.approx(_cosine_similarity(b, a))


# ---------------------------------------------------------------------------
# query_chunks — hybrid re-ranking logic
# ---------------------------------------------------------------------------


def _make_query_result(entries: list[tuple[str, str, dict, float, list[float]]]) -> dict:
    """Build a Chroma-shaped query result dict from a list of (id, doc, meta, dist, emb)."""
    return {
        "ids": [[e[0] for e in entries]],
        "documents": [[e[1] for e in entries]],
        "metadatas": [[e[2] for e in entries]],
        "distances": [[e[3] for e in entries]],
        "embeddings": [[e[4] for e in entries]],
    }


def _unit(v: list[float]) -> list[float]:
    """Return the unit vector of v."""
    norm = sum(x * x for x in v) ** 0.5
    return [x / norm for x in v]


QUERY_VEC = _unit([1.0, 0.0, 0.0])  # Points along x-axis

# Two close-in-L2 documents that differ only slightly in cosine direction
DOC_A_EMB = _unit([1.0, 0.1, 0.0])   # very aligned with query (high cosine)
DOC_B_EMB = _unit([1.0, 0.5, 0.0])   # moderately aligned (lower cosine)


def _mock_collection(count: int, query_result: dict) -> MagicMock:
    col = MagicMock()
    col.count.return_value = count
    col.query.return_value = query_result
    return col


class TestQueryChunksHybrid:
    def _run(self, entries, max_distance=1.5, top_k=4, *, hybrid: bool = True):
        query_result = _make_query_result(entries)
        collection = _mock_collection(len(entries), query_result)

        with (
            patch("src.shared.vector_store.get_client") as mock_get_client,
            patch(
                "src.shared.vector_store._embed_single_cached",
                return_value=tuple(QUERY_VEC),
            ),
            patch.object(vs_module, "HYBRID_RETRIEVAL_ENABLED", hybrid),
        ):
            mock_get_client.return_value.get_or_create_collection.return_value = collection
            return query_chunks("col", "conv-1", "test question", top_k=top_k, max_distance=max_distance)

    def test_returns_empty_for_empty_collection(self):
        collection = _mock_collection(0, {})
        with (
            patch("src.shared.vector_store.get_client") as mock_get_client,
            patch("src.shared.vector_store._embed_single_cached", return_value=tuple(QUERY_VEC)),
        ):
            mock_get_client.return_value.get_or_create_collection.return_value = collection
            result = query_chunks("col", "conv-1", "q", top_k=4)
        assert result == []

    def test_result_contains_hybrid_score_and_cosine_similarity(self):
        l2_dist = 0.02  # very small → documents are near-identical to query
        entry = ("id1", "text", {"file_name": "a.pdf"}, l2_dist, DOC_A_EMB)
        rows = self._run([entry], hybrid=True)

        assert len(rows) == 1
        assert "hybrid_score" in rows[0]
        assert "cosine_similarity" in rows[0]
        assert "distance" in rows[0]

    def test_filters_out_chunks_beyond_max_distance(self):
        far = ("far", "text", {"file_name": "b.pdf"}, 1.9, DOC_B_EMB)
        near = ("near", "text", {"file_name": "a.pdf"}, 0.1, DOC_A_EMB)
        rows = self._run([far, near], max_distance=1.3, hybrid=True)

        ids = [r["chunk_id"] for r in rows]
        assert "far" not in ids
        assert "near" in ids

    def test_result_sorted_by_hybrid_score_descending(self):
        # DOC_A is more cosine-aligned with QUERY_VEC than DOC_B.
        # Both have the same L2 distance, so hybrid score should prefer DOC_A.
        shared_l2 = 0.05
        entries = [
            ("b", "text b", {"file_name": "b.pdf"}, shared_l2, DOC_B_EMB),
            ("a", "text a", {"file_name": "a.pdf"}, shared_l2, DOC_A_EMB),
        ]
        rows = self._run(entries, top_k=4, hybrid=True)

        assert rows[0]["chunk_id"] == "a", (
            "DOC_A should rank first because it has higher cosine similarity "
            "with the query when L2 distances are equal"
        )

    def test_top_k_respected(self):
        entries = [
            (f"id{i}", f"text {i}", {"file_name": "f.pdf"}, 0.1 + i * 0.05, DOC_A_EMB)
            for i in range(8)
        ]
        rows = self._run(entries, top_k=3, hybrid=True)
        assert len(rows) == 3

    def test_fetch_multiplier_applied_to_chroma_query(self):
        """Chroma should be asked for top_k * HYBRID_FETCH_MULTIPLIER candidates."""
        top_k = 2
        entries = [
            (f"id{i}", f"text {i}", {"file_name": "f.pdf"}, 0.1, DOC_A_EMB)
            for i in range(top_k * HYBRID_FETCH_MULTIPLIER)
        ]
        query_result = _make_query_result(entries)
        collection = _mock_collection(20, query_result)

        with (
            patch("src.shared.vector_store.get_client") as mock_get_client,
            patch(
                "src.shared.vector_store._embed_single_cached",
                return_value=tuple(QUERY_VEC),
            ),
            patch.object(vs_module, "HYBRID_RETRIEVAL_ENABLED", True),
        ):
            mock_get_client.return_value.get_or_create_collection.return_value = collection
            query_chunks("col", "conv-1", "q", top_k=top_k)

        call_kwargs = collection.query.call_args.kwargs
        assert call_kwargs["n_results"] == top_k * HYBRID_FETCH_MULTIPLIER

    def test_embeddings_requested_from_chroma(self):
        """The hybrid query must include 'embeddings' so we can compute cosine."""
        entries = [("id1", "text", {"file_name": "f.pdf"}, 0.1, DOC_A_EMB)]
        query_result = _make_query_result(entries)
        collection = _mock_collection(5, query_result)

        with (
            patch("src.shared.vector_store.get_client") as mock_get_client,
            patch(
                "src.shared.vector_store._embed_single_cached",
                return_value=tuple(QUERY_VEC),
            ),
            patch.object(vs_module, "HYBRID_RETRIEVAL_ENABLED", True),
        ):
            mock_get_client.return_value.get_or_create_collection.return_value = collection
            query_chunks("col", "conv-1", "q")

        include_arg = collection.query.call_args.kwargs["include"]
        assert "embeddings" in include_arg

    def test_hybrid_score_formula(self):
        """Verify the hybrid score equals L2_WEIGHT*l2_sim + COSINE_WEIGHT*cosine."""
        l2_dist = 0.4
        doc_emb = DOC_A_EMB
        entry = ("id1", "text", {"file_name": "x.pdf"}, l2_dist, doc_emb)
        rows = self._run([entry], hybrid=True)

        assert len(rows) == 1
        row = rows[0]
        expected_l2_sim = 1.0 - l2_dist / 2.0
        expected_cosine = _cosine_similarity(QUERY_VEC, doc_emb)
        expected_hybrid = HYBRID_L2_WEIGHT * expected_l2_sim + HYBRID_COSINE_WEIGHT * expected_cosine
        assert row["hybrid_score"] == pytest.approx(expected_hybrid, abs=1e-9)
        assert row["cosine_similarity"] == pytest.approx(expected_cosine, abs=1e-9)


# ---------------------------------------------------------------------------
# HYBRID_RETRIEVAL_ENABLED flag dispatch
# ---------------------------------------------------------------------------


class TestHybridRetrievalFlag:
    """Verify that the flag routes to the correct internal implementation."""

    def _call(self, flag: bool) -> MagicMock:
        entries = [("id1", "text", {"file_name": "f.pdf"}, 0.1, DOC_A_EMB)]
        query_result = _make_query_result(entries)
        collection = _mock_collection(5, query_result)

        with (
            patch("src.shared.vector_store.get_client") as mock_get_client,
            patch("src.shared.vector_store._embed_single_cached", return_value=tuple(QUERY_VEC)),
            patch.object(vs_module, "HYBRID_RETRIEVAL_ENABLED", flag),
        ):
            mock_get_client.return_value.get_or_create_collection.return_value = collection
            query_chunks("col", "conv-1", "q")
            return collection

    def test_flag_false_does_not_request_embeddings(self):
        """L2-only path must not ask Chroma for stored embeddings."""
        collection = self._call(False)
        include_arg = collection.query.call_args.kwargs["include"]
        assert "embeddings" not in include_arg

    def test_flag_true_requests_embeddings(self):
        """Hybrid path must ask Chroma for stored embeddings."""
        collection = self._call(True)
        include_arg = collection.query.call_args.kwargs["include"]
        assert "embeddings" in include_arg

    def test_flag_false_fetches_exactly_top_k(self):
        """L2 path should not over-fetch (no multiplier applied)."""
        top_k = 3
        entries = [("id1", "text", {"file_name": "f.pdf"}, 0.1, DOC_A_EMB)]
        query_result = _make_query_result(entries)
        collection = _mock_collection(10, query_result)

        with (
            patch("src.shared.vector_store.get_client") as mock_get_client,
            patch("src.shared.vector_store._embed_single_cached", return_value=tuple(QUERY_VEC)),
            patch.object(vs_module, "HYBRID_RETRIEVAL_ENABLED", False),
        ):
            mock_get_client.return_value.get_or_create_collection.return_value = collection
            query_chunks("col", "conv-1", "q", top_k=top_k)

        assert collection.query.call_args.kwargs["n_results"] == top_k

    def test_flag_false_result_has_no_hybrid_score(self):
        """Rows from the L2 path must not contain hybrid_score or cosine_similarity."""
        entries = [("id1", "text", {"file_name": "f.pdf"}, 0.1, DOC_A_EMB)]
        query_result = _make_query_result(entries)
        # L2 path only uses documents/metadatas/distances — strip embeddings col
        l2_result = {
            "ids": query_result["ids"],
            "documents": query_result["documents"],
            "metadatas": query_result["metadatas"],
            "distances": query_result["distances"],
        }
        collection = _mock_collection(5, l2_result)

        with (
            patch("src.shared.vector_store.get_client") as mock_get_client,
            patch("src.shared.vector_store._embed_single_cached", return_value=tuple(QUERY_VEC)),
            patch.object(vs_module, "HYBRID_RETRIEVAL_ENABLED", False),
        ):
            mock_get_client.return_value.get_or_create_collection.return_value = collection
            rows = query_chunks("col", "conv-1", "q")

        assert len(rows) == 1
        assert "hybrid_score" not in rows[0]
        assert "cosine_similarity" not in rows[0]
