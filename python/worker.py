"""Standalone Cloud Run Job worker for processing a single PDF page.

Designed to run as a Cloud Run Job task. Receives work via environment variables:
  - WORKER_PDF_PATH: GCS URI or local path to PDF
  - WORKER_PAGE_IDX: 0-based page index to process
  - WORKER_TOTAL_PAGES: total page count in PDF
  - WORKER_OUTPUT_DIR: where to save extracted images
  - WORKER_CONVERSATION_ID: conversation ID for telemetry
  - WORKER_COLLECTION_NAME: Chroma collection to upsert into

Flow:
  1. Download PDF page (if GCS URI)
  2. Extract text + images from that single page
  3. Describe images via Vision API
  4. Chunk text
  5. Generate embeddings + upsert to Chroma
  6. Report status to processing_jobs table

Libraries are pre-loaded in the Docker image (no cold-start penalty for imports).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import sentry_sdk

def _before_send_log(log, _hint):
    if os.getenv("SENTRY_ENVIRONMENT", "dev") == "prod" and log["severity_text"] == "debug":
        return None
    return log

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("SENTRY_ENVIRONMENT", "dev"),
    send_default_pii=True,
    traces_sample_rate=1.0,
    max_value_length=8192,
    enable_logs=True,
    before_send_log=_before_send_log,
)

from shared.page_worker import process_pdf_page
from shared.vector_store import upsert_chunks
from shared.chunkers import Chunk
from shared.telemetry import log_processing_event, close_db_pool
from sentry_sdk import logger as sentry_logger

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _image_chunks(images: list[dict]) -> list[Chunk]:
    """Convert image dicts to Chunk objects for vector upsert."""
    chunks = []
    for idx, img in enumerate(images):
        abs_path = Path(img["image_path"])
        image_name = abs_path.name
        page = img["page"]
        section = f"Image (page {page})" if page is not None else "Image"
        chunks.append(Chunk(
            chunk_id=f"{Path(img['file_name']).stem}_img_{idx}",
            file_name=img["file_name"],
            text=img["description"],
            section=section,
            page=page,
            metadata={
                "is_image": True,
                "image_name": image_name,
            },
        ))
    return chunks


def main():
    pdf_path = os.environ.get("WORKER_PDF_PATH")
    page_idx = int(os.environ.get("WORKER_PAGE_IDX", "0"))
    total_pages = int(os.environ.get("WORKER_TOTAL_PAGES", "1"))
    output_dir = os.environ.get("WORKER_OUTPUT_DIR", "/tmp/worker-output")
    conversation_id = os.environ.get("WORKER_CONVERSATION_ID", "unknown")
    collection_name = os.environ.get("WORKER_COLLECTION_NAME", "unknown")

    if not pdf_path:
        logger.error("WORKER_PDF_PATH not set")
        sys.exit(1)

    worker_id = f"cloudrun-{uuid.uuid4().hex[:8]}"
    logger.info(f"🚀 Worker {worker_id} starting: page {page_idx + 1}/{total_pages} of {pdf_path}")
    sentry_logger.info(
        "Worker started for conversation {conversation_id}",
        conversation_id=conversation_id,
        attributes={
            "worker_id": worker_id,
            "page_idx": page_idx,
            "total_pages": total_pages,
            "pdf_path": pdf_path,
            "collection_name": collection_name,
        },
    )

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # If GCS URI, download locally first
    local_pdf = pdf_path
    if pdf_path.startswith("gs://"):
        from google.cloud import storage as gcs
        client = gcs.Client()
        bucket_name = pdf_path.split("/")[2]
        blob_path = "/".join(pdf_path.split("/")[3:])
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        local_pdf = f"/tmp/{Path(blob_path).name}"
        blob.download_to_filename(local_pdf)
        logger.info(f"📥 Downloaded {pdf_path} → {local_pdf}")

    seen_xrefs: set[int] = set()

    try:
        result = process_pdf_page(
            local_pdf, page_idx, total_pages, output_dir,
            conversation_id, seen_xrefs, worker_id,
        )

        if result.error:
            logger.error(f"❌ Page processing failed: {result.error}")
            sys.exit(1)

        # Upsert page chunks + image chunks to Chroma
        all_chunks = list(result.chunks)
        if result.images:
            all_chunks.extend(_image_chunks(result.images))

        if all_chunks:
            logger.info(f"📦 Upserting {len(all_chunks)} chunks to {collection_name}")
            upsert_chunks(
                collection_name=collection_name,
                conversation_id=conversation_id,
                chunks=all_chunks,
            )

        log_processing_event(
            conversation_id, result.file_name, "worker_completed",
            page_number=page_idx + 1, total_pages=total_pages,
            status="completed",
            detail=f"{len(result.chunks)} text chunks, {len(result.images)} images, {result.duration_ms}ms",
            worker_id=worker_id,
        )

        # Output result as JSON for parent process to read
        output = {
            "page": page_idx + 1,
            "chunks": len(all_chunks),
            "images": len(result.images),
            "duration_ms": result.duration_ms,
            "worker_id": worker_id,
        }
        sentry_logger.info(
            "Worker completed for conversation {conversation_id}",
            conversation_id=conversation_id,
            attributes={
                "worker_id": worker_id,
                "page_idx": page_idx,
                "chunk_count": len(all_chunks),
                "image_count": len(result.images),
                "duration_ms": result.duration_ms,
            },
        )
        print(json.dumps(output))

    except Exception as e:
        sentry_sdk.capture_exception(e)
        sentry_logger.fatal(
            "Worker crashed for conversation {conversation_id}",
            conversation_id=conversation_id,
            attributes={
                "worker_id": worker_id,
                "page_idx": page_idx,
                "error": str(e)[:500],
            },
        )
        log_processing_event(
            conversation_id, Path(pdf_path).name, "worker_failed",
            page_number=page_idx + 1, total_pages=total_pages,
            status="failed", error_message=str(e)[:500],
            worker_id=worker_id,
        )
        logger.exception(f"❌ Worker crashed: {e}")
        sys.exit(1)
    finally:
        close_db_pool()


if __name__ == "__main__":
    main()
