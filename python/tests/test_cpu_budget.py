"""Unit tests for ``shared.cpu_budget``.

No DB / GCP dependencies — safe in every CI lane.
"""

from __future__ import annotations

import threading

import pytest

from shared import cpu_budget
from shared.cpu_budget import (
    CpuBudgetExhausted,
    available_slots,
    current_policy,
    estimate_slots_for_file,
    release,
    reserve,
    try_reserve,
)


@pytest.fixture(autouse=True)
def _fresh_budget(monkeypatch):
    """Reset the module-level semaphore for each test so ordering
    doesn't matter. We pin MAIN_MAX_CPU to 4 so the math is obvious.
    """
    monkeypatch.setattr(cpu_budget, "MAIN_MAX_CPU", 4)
    monkeypatch.setattr(cpu_budget, "_budget", threading.BoundedSemaphore(4))
    monkeypatch.setattr(cpu_budget, "_in_use", 0)
    yield


def test_reserve_and_release_tracks_slots():
    assert available_slots() == 4
    assert try_reserve(2) is True
    assert available_slots() == 2
    release(2)
    assert available_slots() == 4


def test_reserve_rejects_over_budget():
    assert try_reserve(3) is True
    assert try_reserve(2) is False  # only 1 free, 2 requested
    assert available_slots() == 1


def test_reserve_context_manager_releases_on_exit():
    with reserve(2):
        assert available_slots() == 2
    assert available_slots() == 4


def test_reserve_context_manager_releases_on_exception():
    with pytest.raises(RuntimeError, match="boom"), reserve(3):
        raise RuntimeError("boom")
    assert available_slots() == 4


def test_reserve_raises_when_exhausted():
    try_reserve(4)
    with pytest.raises(CpuBudgetExhausted), reserve(1):
        pytest.fail("should not enter body")


def test_policy_snapshot_is_readable():
    p = current_policy()
    assert p.cpu_count >= 1
    assert p.main_max_cpu >= 1


def test_estimate_slots_non_pdf_is_one(tmp_path):
    f = tmp_path / "img.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert estimate_slots_for_file(str(f)) == 1


def test_estimate_slots_large_file_two_slots(tmp_path, monkeypatch):
    # Force the page-count probe to report "many pages" without needing a real PDF.
    monkeypatch.setattr(cpu_budget, "_pdf_page_count", lambda _p: 200)
    monkeypatch.setattr(cpu_budget, "_SMALL_FILE_MAX_PAGES", 50)
    monkeypatch.setattr(cpu_budget, "_SMALL_FILE_MAX_BYTES", 5 * 1024 * 1024)

    f = tmp_path / "big.pdf"
    f.write_bytes(b"%PDF-1.4\n" + b"0" * (6 * 1024 * 1024))  # > 5MB
    assert estimate_slots_for_file(str(f)) == 2


def test_estimate_slots_small_pdf_one_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(cpu_budget, "_pdf_page_count", lambda _p: 10)
    monkeypatch.setattr(cpu_budget, "_SMALL_FILE_MAX_PAGES", 50)
    monkeypatch.setattr(cpu_budget, "_SMALL_FILE_MAX_BYTES", 5 * 1024 * 1024)

    f = tmp_path / "small.pdf"
    f.write_bytes(b"%PDF-1.4\nsmall")
    assert estimate_slots_for_file(str(f)) == 1


def test_estimate_slots_missing_file_defaults_to_one(tmp_path):
    assert estimate_slots_for_file(str(tmp_path / "nope.pdf")) == 1
