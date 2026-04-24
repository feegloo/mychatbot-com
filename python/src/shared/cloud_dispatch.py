"""Cloud worker mode detection.

Only ``is_cloud_mode()`` remains — the per-page Cloud Run Jobs dispatcher was
removed when we switched to whole-PDF pulls via the chatrag-worker Cloud Run
Worker Pool (see ``python/worker_pubsub.py``). The streaming OCR pipeline in
``indexing.py`` uses ``is_cloud_mode()`` to decide whether to run the
hybrid-streaming variant (which upserts chunks per page) versus the local
batch variant.
"""

from __future__ import annotations

import os


def is_cloud_mode() -> bool:
    mode = os.getenv("WORKER_MODE", "local").lower()
    return mode in ("cloud_run", "pubsub_worker")
