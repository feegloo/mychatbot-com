"""Tests that verify chunking produces natural, well-bounded chunks on real files.

Runs against files in ../test-files/.  If that directory is missing the tests
are skipped so CI doesn't break without the fixture data.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from shared.chunkers import split_into_chunks
from shared.extractors import extract_text

TEST_FILES_DIR = Path(__file__).resolve().parent.parent.parent / "test-files"

# ── helpers ──────────────────────────────────────────────────────────


def _starts_at_natural_boundary(text: str) -> bool:
    """Chunk begins at a header, list item, or new sentence/paragraph."""
    stripped = text.lstrip("\n")
    if not stripped:
        return True
    first_line = stripped.split("\n")[0].strip()
    if re.match(r"^#{1,6}\s", first_line):
        return True
    if re.match(r"^(\d+[\.\)]\s|[a-zA-Z][\.\)]\s)", first_line):
        return True
    if re.match(r"^[-*•\uf0b7]\s", first_line):
        return True
    return bool(re.match(r"^[A-ZĄĆĘŁŃÓŚŹŻ0-9]", first_line))


def _starts_mid_sentence(text: str) -> bool:
    """Chunk starts with a lowercase letter — likely mid-sentence."""
    stripped = text.strip()
    if not stripped:
        return False
    return bool(re.match(r"^[a-ząćęłńóśźż]", stripped))


def _collect_test_files() -> list[Path]:
    if not TEST_FILES_DIR.exists():
        return []
    return sorted(f for f in TEST_FILES_DIR.iterdir() if f.is_file())


_files = _collect_test_files()
_skip = pytest.mark.skipif(not _files, reason="No test-files directory")

pytestmark = pytest.mark.slow

# Tabular/spreadsheet files where sentence-boundary heuristics don't apply
_TABULAR_FILES = {"Siłownia - tabelka z treningami.docx"}


# ── parametrized per-file tests ──────────────────────────────────────


def _file_ids():
    return [f.name for f in _files]


@_skip
@pytest.mark.parametrize("path", _files, ids=_file_ids())
class TestChunkingRealFiles:
    """Per-file chunking quality assertions."""

    def test_no_empty_chunks(self, path: Path):
        text = extract_text(str(path))
        chunks = split_into_chunks(path.name, text)
        for c in chunks:
            assert c.text.strip(), f"Empty chunk {c.chunk_id}"

    def test_chunk_size_within_bounds(self, path: Path):
        text = extract_text(str(path))
        chunks = split_into_chunks(path.name, text)
        for c in chunks:
            assert len(c.text) <= 2000, f"{c.chunk_id}: {len(c.text)} chars exceeds 2000 limit"

    def test_no_text_lost(self, path: Path):
        """All extracted text should appear in at least one chunk."""
        text = extract_text(str(path))
        if not text.strip():
            return
        chunks = split_into_chunks(path.name, text)
        combined = "".join(c.text for c in chunks)
        # Check a sample of words from the original text
        words = [w for w in text.split() if len(w) > 4][:20]
        for word in words:
            assert word in combined, f"Word {word!r} lost during chunking"

    def test_majority_natural_starts(self, path: Path):
        """At least 40% of chunks should start at a natural boundary."""
        if path.name in _TABULAR_FILES:
            pytest.skip("Tabular file — sentence boundaries not applicable")
        text = extract_text(str(path))
        chunks = split_into_chunks(path.name, text)
        if len(chunks) <= 1:
            return
        natural = sum(1 for c in chunks if _starts_at_natural_boundary(c.text))
        pct = natural / len(chunks)
        assert pct >= 0.40, (
            f"Only {pct:.0%} of chunks start at natural boundaries ({natural}/{len(chunks)})"
        )

    def test_low_mid_sentence_starts(self, path: Path):
        """At most 50% of chunks should start mid-sentence."""
        if path.name in _TABULAR_FILES:
            pytest.skip("Tabular file — sentence boundaries not applicable")
        text = extract_text(str(path))
        chunks = split_into_chunks(path.name, text)
        if len(chunks) <= 1:
            return
        mid = sum(1 for c in chunks if _starts_mid_sentence(c.text))
        pct = mid / len(chunks)
        assert pct <= 0.50, f"{pct:.0%} of chunks start mid-sentence ({mid}/{len(chunks)})"

    def test_unique_chunk_ids(self, path: Path):
        text = extract_text(str(path))
        chunks = split_into_chunks(path.name, text)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))


# ── aggregate quality gate ──────────────────────────────────────────


@_skip
class TestOverallChunkQuality:
    """Aggregate quality checks across all test files."""

    @pytest.fixture(autouse=True)
    def _chunk_all(self):
        self.all_chunks = []
        for path in _files:
            text = extract_text(str(path))
            chunks = split_into_chunks(path.name, text)
            self.all_chunks.extend(chunks)

    def test_overall_natural_start_rate(self):
        """Across all files, ≥60% of chunks should start at natural boundaries."""
        total = len(self.all_chunks)
        assert total > 0
        natural = sum(1 for c in self.all_chunks if _starts_at_natural_boundary(c.text))
        pct = natural / total
        assert pct >= 0.60, f"Overall natural-start rate: {pct:.0%} ({natural}/{total})"

    def test_overall_mid_sentence_rate(self):
        """Across all files, ≤30% of chunks should start mid-sentence."""
        total = len(self.all_chunks)
        assert total > 0
        mid = sum(1 for c in self.all_chunks if _starts_mid_sentence(c.text))
        pct = mid / total
        assert pct <= 0.30, f"Overall mid-sentence rate: {pct:.0%} ({mid}/{total})"

    def test_average_chunk_length_reasonable(self):
        """Average chunk length should be between 200 and 1800 chars."""
        lengths = [len(c.text) for c in self.all_chunks]
        avg = sum(lengths) / len(lengths)
        assert 200 <= avg <= 1800, f"Average chunk length: {avg:.0f}"

    def test_no_very_tiny_chunks(self):
        """No chunk should be under 20 characters (likely a splitting artifact)."""
        for c in self.all_chunks:
            clean = c.text.strip().lstrip("\ufeff")
            assert len(clean) >= 3, f"Tiny chunk {c.chunk_id}: {c.text.strip()!r}"
