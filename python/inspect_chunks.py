#!/usr/bin/env python
"""Inspect chunking quality on real test files.

Usage:
    python inspect_chunks.py                    # all files in ../test-files
    python inspect_chunks.py path/to/file.pdf   # single file
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from shared.extractors import extract_text
from shared.chunkers import split_into_chunks

TEST_FILES_DIR = Path(__file__).resolve().parent.parent / "test-files"

# ── Chunk-quality heuristics ────────────────────────────────────────


def starts_at_natural_boundary(text: str) -> bool:
    """Check if a chunk begins at a natural boundary (header, bullet, numbered item, paragraph start)."""
    stripped = text.lstrip("\n")
    if not stripped:
        return True
    first_line = stripped.split("\n")[0].strip()
    # Markdown header
    if re.match(r"^#{1,6}\s", first_line):
        return True
    # Numbered list item  (1. / 2) / a) etc.)
    if re.match(r"^(\d+[\.\)]\s|[a-zA-Z][\.\)]\s)", first_line):
        return True
    # Bullet  (- / * / •)
    if re.match(r"^[-*•]\s", first_line):
        return True
    # Begins with uppercase letter or digit (new sentence / paragraph)
    if re.match(r"^[A-ZĄĆĘŁŃÓŚŹŻ0-9]", first_line):
        return True
    return False


def ends_at_natural_boundary(text: str) -> bool:
    """Check if a chunk ends at a natural boundary (sentence-end, blank line, list item end)."""
    stripped = text.rstrip()
    if not stripped:
        return True
    last_char = stripped[-1]
    # Ends with sentence-ending punctuation or colon
    if last_char in ".!?:;…)\"'":
        return True
    # Ends with a blank line before stripping
    if text.rstrip(" ").endswith("\n\n"):
        return True
    return False


def has_mid_sentence_break(text: str) -> bool:
    """Detect if the chunk starts or ends mid-sentence (heuristic)."""
    stripped = text.strip()
    if not stripped:
        return False
    # Starts with lowercase letter (likely mid-sentence)
    if re.match(r"^[a-ząćęłńóśźż]", stripped):
        return True
    return False


def chunk_quality_report(file_name: str, text: str) -> dict:
    """Produce a quality report for chunking a single file."""
    chunks = split_into_chunks(file_name, text)
    total = len(chunks)
    if total == 0:
        return {"file": file_name, "chunks": 0, "chars": len(text)}

    natural_starts = sum(1 for c in chunks if starts_at_natural_boundary(c.text))
    natural_ends = sum(1 for c in chunks if ends_at_natural_boundary(c.text))
    mid_sentence = sum(1 for c in chunks if has_mid_sentence_break(c.text))
    lengths = [len(c.text) for c in chunks]

    return {
        "file": file_name,
        "chars": len(text),
        "chunks": total,
        "natural_start_pct": round(100 * natural_starts / total),
        "natural_end_pct": round(100 * natural_ends / total),
        "mid_sentence_pct": round(100 * mid_sentence / total),
        "avg_len": round(sum(lengths) / total),
        "min_len": min(lengths),
        "max_len": max(lengths),
    }


def print_chunks_detail(file_name: str, text: str) -> None:
    """Print each chunk with boundary indicators."""
    chunks = split_into_chunks(file_name, text)
    print(f"\n{'='*80}")
    print(f"FILE: {file_name}  ({len(text)} chars → {len(chunks)} chunks)")
    print(f"{'='*80}")
    for i, chunk in enumerate(chunks):
        ns = "✓" if starts_at_natural_boundary(chunk.text) else "✗"
        ne = "✓" if ends_at_natural_boundary(chunk.text) else "✗"
        ms = " ⚠MID-SENT" if has_mid_sentence_break(chunk.text) else ""
        preview_start = chunk.text[:80].replace("\n", "\\n")
        preview_end = chunk.text[-60:].replace("\n", "\\n")
        print(f"\n  [{i}] {len(chunk.text):>5} chars  start:{ns}  end:{ne}{ms}")
        print(f"       section: {chunk.section}")
        print(f"       begin: {preview_start!r}")
        print(f"       end:   {preview_end!r}")


def main():
    if len(sys.argv) > 1:
        paths = [Path(a) for a in sys.argv[1:]]
    else:
        if not TEST_FILES_DIR.exists():
            print(f"No test-files directory at {TEST_FILES_DIR}")
            sys.exit(1)
        paths = sorted(TEST_FILES_DIR.iterdir())

    reports = []
    for path in paths:
        if not path.is_file():
            continue
        text = extract_text(str(path))
        report = chunk_quality_report(path.name, text)
        reports.append(report)
        print_chunks_detail(path.name, text)

    # Summary table
    print(f"\n\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"{'File':<50} {'Chunks':>6} {'Start%':>7} {'End%':>6} {'MidSent%':>9} {'AvgLen':>7}")
    print("-" * 90)
    for r in reports:
        if r["chunks"] == 0:
            print(f"{r['file']:<50} {'(empty)':>6}")
            continue
        print(
            f"{r['file']:<50} {r['chunks']:>6} {r['natural_start_pct']:>6}% "
            f"{r['natural_end_pct']:>5}% {r['mid_sentence_pct']:>8}% {r['avg_len']:>7}"
        )


if __name__ == "__main__":
    main()
