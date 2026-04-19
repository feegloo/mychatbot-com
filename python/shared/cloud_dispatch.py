"""Cloud Run Jobs dispatcher for delegating PDF page work to remote workers.

When WORKER_MODE=cloud_run, the indexing pipeline dispatches per-page jobs
to Cloud Run instead of processing locally with ThreadPoolExecutor.

Requirements:
  - gcloud CLI or google-cloud-run library
  - Pre-built worker image pushed to Artifact Registry
  - Cloud Run Job created: `chatrag-worker`

Set environment variables:
  WORKER_MODE=cloud_run          # Enable cloud dispatch (default: local)
  WORKER_JOB_NAME=chatrag-worker # Cloud Run Job name
  WORKER_REGION=europe-west1     # GCP region
  GCP_PROJECT_ID=chatbotqa-app   # GCP project
"""

from __future__ import annotations

import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


def is_cloud_mode() -> bool:
    return os.getenv("WORKER_MODE", "local").lower() == "cloud_run"


def dispatch_page_jobs(
    pdf_gcs_uri: str,
    total_pages: int,
    output_dir: str,
    conversation_id: str,
    collection_name: str,
) -> list[dict]:
    """Dispatch one Cloud Run Job execution per page.

    Each task processes a single page. We override env vars per execution.
    Returns list of execution results.
    """
    job_name = os.getenv("WORKER_JOB_NAME", "chatrag-worker")
    region = os.getenv("WORKER_REGION", "europe-west1")
    project = os.getenv("GCP_PROJECT_ID", "chatbotqa-app")

    logger.info(
        f"☁️ Dispatching {total_pages} Cloud Run Job tasks: "
        f"job={job_name} region={region} project={project}"
    )

    results: list[dict] = []

    # Dispatch all pages in parallel (gcloud calls are IO-bound)
    def _dispatch_one(page_idx: int) -> dict:
        env_overrides = ",".join(
            [
                f"WORKER_PDF_PATH={pdf_gcs_uri}",
                f"WORKER_PAGE_IDX={page_idx}",
                f"WORKER_TOTAL_PAGES={total_pages}",
                f"WORKER_OUTPUT_DIR={output_dir}",
                f"WORKER_CONVERSATION_ID={conversation_id}",
                f"WORKER_COLLECTION_NAME={collection_name}",
            ]
        )

        cmd = [
            "gcloud",
            "run",
            "jobs",
            "execute",
            job_name,
            f"--region={region}",
            f"--project={project}",
            f"--update-env-vars={env_overrides}",
            "--tasks=1",
            "--wait",  # Wait for completion
            "--format=json",
        ]

        logger.info(f"☁️ Dispatching page {page_idx + 1}/{total_pages}")
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if proc.returncode == 0:
                return {
                    "page": page_idx + 1,
                    "status": "completed",
                    "output": proc.stdout[:500],
                }
            else:
                return {
                    "page": page_idx + 1,
                    "status": "failed",
                    "error": proc.stderr[:500],
                }
        except subprocess.TimeoutExpired:
            return {
                "page": page_idx + 1,
                "status": "failed",
                "error": "Cloud Run Job timed out after 600s",
            }
        except Exception as e:
            return {
                "page": page_idx + 1,
                "status": "failed",
                "error": str(e)[:500],
            }

    # Use ThreadPool to dispatch gcloud commands concurrently
    max_concurrent = min(total_pages, 20)  # Cap concurrent dispatches
    with ThreadPoolExecutor(max_workers=max_concurrent) as pool:
        futures = {pool.submit(_dispatch_one, idx): idx for idx in range(total_pages)}
        for future in as_completed(futures):
            results.append(future.result())

    succeeded = sum(1 for r in results if r["status"] == "completed")
    logger.info(f"☁️ Cloud Run Jobs: {succeeded}/{total_pages} pages completed")
    return sorted(results, key=lambda r: r["page"])
