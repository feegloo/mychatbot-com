#!/usr/bin/env python3
"""Benchmark PDF page extraction speed with varying worker counts.

Usage:
  python3.11 bench_pdf_parse.py test-files/Mroz-Remigiusz-Joanna-Chylka-02-Zaginiecie.pdf
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

import fitz  # PyMuPDF


def extract_page_text(pdf_path: str, page_idx: int) -> tuple[int, str, int]:
    """Extract text from a single page. Returns (page_idx, text, char_count)."""
    doc = fitz.open(pdf_path)
    page = doc[page_idx]
    text = page.get_text() or ""
    doc.close()
    return page_idx, text, len(text)


def extract_page_text_shared_doc(args: tuple) -> tuple[int, int]:
    """For measuring raw text extraction speed (no doc open overhead)."""
    pdf_path, page_idx = args
    doc = fitz.open(pdf_path)
    page = doc[page_idx]
    text = page.get_text() or ""
    doc.close()
    return page_idx, len(text)


def bench_sequential(pdf_path: str, total_pages: int) -> float:
    """Baseline: sequential page extraction."""
    start = time.monotonic()
    doc = fitz.open(pdf_path)
    total_chars = 0
    for i in range(total_pages):
        page = doc[i]
        text = page.get_text() or ""
        total_chars += len(text)
    doc.close()
    elapsed = time.monotonic() - start
    print(f"  Sequential (single doc):    {elapsed:.2f}s  ({total_chars:,} chars)")
    return elapsed


def bench_sequential_per_page_open(pdf_path: str, total_pages: int) -> float:
    """Sequential but open/close doc per page (like worker does)."""
    start = time.monotonic()
    total_chars = 0
    for i in range(total_pages):
        doc = fitz.open(pdf_path)
        page = doc[i]
        text = page.get_text() or ""
        total_chars += len(text)
        doc.close()
    elapsed = time.monotonic() - start
    print(f"  Sequential (per-page open): {elapsed:.2f}s  ({total_chars:,} chars)")
    return elapsed


def bench_thread_pool(pdf_path: str, total_pages: int, workers: int) -> float:
    """ThreadPoolExecutor with N workers."""
    start = time.monotonic()
    total_chars = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(extract_page_text, pdf_path, i): i
            for i in range(total_pages)
        }
        for f in as_completed(futures):
            _, _, chars = f.result()
            total_chars += chars
    elapsed = time.monotonic() - start
    print(f"  ThreadPool ({workers:2d} workers):   {elapsed:.2f}s  ({total_chars:,} chars)")
    return elapsed


def bench_process_pool(pdf_path: str, total_pages: int, workers: int) -> float:
    """ProcessPoolExecutor with N workers."""
    start = time.monotonic()
    total_chars = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(extract_page_text, pdf_path, i): i
            for i in range(total_pages)
        }
        for f in as_completed(futures):
            _, _, chars = f.result()
            total_chars += chars
    elapsed = time.monotonic() - start
    print(f"  ProcessPool ({workers:2d} workers):  {elapsed:.2f}s  ({total_chars:,} chars)")
    return elapsed


def bench_full_pipeline_simulation(pdf_path: str, total_pages: int, workers: int) -> float:
    """Simulate full page processing: extract + reflow + chunk (no API calls)."""
    # Import chunker
    sys.path.insert(0, str(Path(__file__).parent))
    from shared.chunkers import split_into_chunks
    from shared.extractors import _reflow_pdf_text, _sanitize_text

    start = time.monotonic()
    total_chunks = 0

    def process_page(page_idx: int) -> int:
        doc = fitz.open(pdf_path)
        page = doc[page_idx]
        raw = page.get_text() or ""
        doc.close()
        reflowed = _reflow_pdf_text(raw.strip())
        text = _sanitize_text(f"# Page {page_idx + 1}\n\n{reflowed}")
        chunks = split_into_chunks(Path(pdf_path).name, text, page_num=page_idx + 1)
        return len(chunks)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(process_page, i) for i in range(total_pages)]
        for f in as_completed(futures):
            total_chunks += f.result()

    elapsed = time.monotonic() - start
    print(f"  Full pipeline ({workers:2d} workers): {elapsed:.2f}s  ({total_chunks} chunks)")
    return elapsed


def main():
    if len(sys.argv) < 2:
        print("Usage: python3.11 bench_pdf_parse.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.isabs(pdf_path):
        pdf_path = os.path.join(os.getcwd(), pdf_path)

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    cpu_count = os.cpu_count() or 1
    print(f"\n{'='*60}")
    print(f"PDF: {Path(pdf_path).name}")
    print(f"Pages: {total_pages}")
    print(f"Size: {os.path.getsize(pdf_path) / 1024:.0f} KB")
    print(f"CPU cores: {cpu_count}")
    print(f"{'='*60}\n")

    print("=== Raw text extraction benchmarks ===")
    t_seq = bench_sequential(pdf_path, total_pages)
    bench_sequential_per_page_open(pdf_path, total_pages)
    print()

    print("=== ThreadPoolExecutor benchmarks ===")
    for w in [1, 2, 4, 8, 16]:
        if w <= cpu_count * 2:
            t = bench_thread_pool(pdf_path, total_pages, w)
            print(f"       speedup vs sequential: {t_seq/t:.1f}x")
    print()

    print("=== ProcessPoolExecutor benchmarks ===")
    for w in [2, 4, 8]:
        if w <= cpu_count:
            t = bench_process_pool(pdf_path, total_pages, w)
            print(f"       speedup vs sequential: {t_seq/t:.1f}x")
    print()

    print("=== Full pipeline (extract + reflow + chunk) ===")
    for w in [1, 2, 4, 8]:
        if w <= cpu_count * 2:
            t = bench_full_pipeline_simulation(pdf_path, total_pages, w)
            print(f"       speedup vs sequential: {t_seq/t:.1f}x")

    print(f"\n{'='*60}")
    print("Note: Production adds API calls (OCR, Vision, embeddings)")
    print("which are IO-bound and benefit MORE from parallelism.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
