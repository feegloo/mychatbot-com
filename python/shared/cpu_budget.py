"""CPU budget allocator for the main chatrag instance.

Enforces the processing policy:
  * Main instance uses at most 50% of system CPUs for indexing.
  * Always leave at least 1 CPU free for backend HTTP traffic.
  * Each file reserves 1 or 2 CPU "slots" depending on size / page count.
  * When a new file can't fit in the remaining budget, the caller
    should delegate to the chatrag-worker service via Pub/Sub.

This is a **soft** limit — slots are counted via a bounded semaphore;
actual per-file parallelism is handled inside ``page_worker.py`` via
``PDF_PAGE_WORKERS``/``PDF_IMAGE_WORKERS``. The budget here prevents
thread-pool explosion when many uploads arrive at once.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Policy knobs (env overridable) ───────────────────────────────────
_CPU_COUNT = os.cpu_count() or 2

# How many CPUs the main instance is allowed to spend on indexing.
# Default: 50% of system CPUs, minus 1 reserved for backend request
# handling, clamped to at least 1.
_RESERVED_FOR_BACKEND = int(os.environ.get("CPU_RESERVED_FOR_BACKEND", "1"))
_MAIN_MAX_CPU_DEFAULT = max(1, (_CPU_COUNT // 2))
MAIN_MAX_CPU = max(
    1,
    min(
        _CPU_COUNT - _RESERVED_FOR_BACKEND,
        int(os.environ.get("CPU_MAIN_MAX", str(_MAIN_MAX_CPU_DEFAULT))),
    ),
)

# Heuristic thresholds for "small" files that need only 1 CPU slot.
# Anything larger reserves 2 slots. Overridable so ops can retune
# without a code change.
_SMALL_FILE_MAX_BYTES = int(os.environ.get("CPU_SMALL_FILE_MAX_BYTES", str(5 * 1024 * 1024)))
_SMALL_FILE_MAX_PAGES = int(os.environ.get("CPU_SMALL_FILE_MAX_PAGES", "50"))


@dataclass(frozen=True)
class CpuPolicy:
    """Snapshot of the current policy, useful for logging and tests."""

    cpu_count: int
    reserved_for_backend: int
    main_max_cpu: int
    small_file_max_bytes: int
    small_file_max_pages: int


def current_policy() -> CpuPolicy:
    return CpuPolicy(
        cpu_count=_CPU_COUNT,
        reserved_for_backend=_RESERVED_FOR_BACKEND,
        main_max_cpu=MAIN_MAX_CPU,
        small_file_max_bytes=_SMALL_FILE_MAX_BYTES,
        small_file_max_pages=_SMALL_FILE_MAX_PAGES,
    )


def _pdf_page_count(file_path: str) -> int | None:
    """Fast PDF page-count lookup. Returns ``None`` on failure so
    callers fall back to file-size-only heuristic.
    """
    try:
        import fitz  # PyMuPDF

        with fitz.open(file_path) as doc:
            return doc.page_count
    except Exception as e:
        logger.debug(f"pdf_page_count({file_path}) failed: {e}")
        return None


def estimate_slots_for_file(file_path: str) -> int:
    """Return 1 or 2 — the number of CPU slots to reserve for this file.

    Heuristic:
      * Small & few pages → 1 slot (fast text PDFs, images, .docx)
      * Large OR many pages → 2 slots (scanned books, complex layouts)

    Rule is intentionally coarse; the inner page-worker loop already
    scales threads within the allocated CPU budget.
    """
    path = Path(file_path)
    try:
        size = path.stat().st_size
    except OSError:
        # File doesn't exist yet (e.g. about-to-be-downloaded GCS fallback):
        # assume small to avoid blocking the pipeline on metadata.
        return 1

    suffix = path.suffix.lower()
    if suffix != ".pdf":
        # Non-PDFs are single-unit — always cheap.
        return 1

    if size <= _SMALL_FILE_MAX_BYTES:
        pages = _pdf_page_count(str(path))
        if pages is None or pages <= _SMALL_FILE_MAX_PAGES:
            return 1
    return 2


# ── Slot accounting ──────────────────────────────────────────────────
# BoundedSemaphore over-release raises ValueError — handy sanity check.
_budget = threading.BoundedSemaphore(MAIN_MAX_CPU)
_budget_lock = threading.Lock()
_in_use = 0


def available_slots() -> int:
    with _budget_lock:
        return MAIN_MAX_CPU - _in_use


def try_reserve(slots: int) -> bool:
    """Reserve ``slots`` atomically. Returns ``True`` on success.

    A job requesting more slots than ``MAIN_MAX_CPU`` will always be
    rejected here — callers should delegate it to the worker service.
    """
    if slots <= 0:
        return True
    global _in_use
    with _budget_lock:
        if _in_use + slots > MAIN_MAX_CPU:
            return False
        acquired = 0
        for _ in range(slots):
            if not _budget.acquire(blocking=False):
                # Shouldn't happen since we hold _budget_lock, but stay defensive.
                for _ in range(acquired):
                    _budget.release()
                return False
            acquired += 1
        _in_use += slots
        return True


def release(slots: int) -> None:
    if slots <= 0:
        return
    global _in_use
    with _budget_lock:
        for _ in range(slots):
            _budget.release()
        _in_use -= slots


@contextmanager
def reserve(slots: int):
    """Context manager — reserves or raises ``CpuBudgetExhausted``."""
    if not try_reserve(slots):
        raise CpuBudgetExhausted(
            f"cannot reserve {slots} CPU slot(s); "
            f"{available_slots()}/{MAIN_MAX_CPU} free"
        )
    try:
        yield
    finally:
        release(slots)


class CpuBudgetExhausted(RuntimeError):
    """Raised by ``reserve`` when the requested slot count is unavailable.

    Callers should catch this and delegate the job to a remote worker.
    """


logger.info(
    f"🧮 CPU budget initialized: total={_CPU_COUNT}, "
    f"main_max={MAIN_MAX_CPU}, reserved_for_backend={_RESERVED_FOR_BACKEND}"
)
