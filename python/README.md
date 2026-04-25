# Python engine

Production runtime for indexing uploaded files and answering questions over them.

## Entry points

All Python source lives under `src/` (shared modules under `src/shared/`).

- `src/server.py` — long-running FastAPI server. Backend calls it over HTTP (`/index`, `/answer`, `/enrich-metadata`, etc.). Primary production runtime.
- `src/worker_pubsub.py` — Cloud Run Worker that pulls indexing jobs from GCP Pub/Sub (GCP prod).
- `src/index_documents.py` — one-shot CLI wrapper around `shared.indexing` for local debugging.
- `src/answer_question.py` — one-shot CLI wrapper around `shared.rag`.
- `src/inspect_chunks.py` — debug helper: dumps chunker output for a file.
- `src/bench_pdf_parse.py` — micro-benchmark for the PDF extraction path.

## src/shared/ layout

| Module | Purpose |
|---|---|
| `indexing.py` | Orchestrates upload → extract → chunk → embed → store |
| `extractors.py` | PDF / DOCX / XLSX / TXT / image extraction |
| `chunkers.py` | Paragraph- and heading-aware chunking with overlap |
| `chapters.py` | Chapter detection + page → chapter map |
| `vector_store.py` | Chroma upsert + query, per-conversation collection |
| `rag.py` | Answer pipeline (retrieval, prompt build, LLM, citations) |
| `describe.py` | Welcome-message generation per uploaded file |
| `suggested_questions.py` | Click-to-ask prompts after a file is indexed |
| `prompts/` | All system prompts (welcome, assistant, quiz, shared labels & actions) |
| `page_worker.py`, `streaming_pdf.py`, `pdf_pages_db.py` | Per-page streaming PDF pipeline |
| `metadata.py` | EXIF + Vision API enrichment |
| `lang_detect.py` | Language detection |
| `telemetry.py`, `otel.py`, `llm_instrument.py` | Tracing + LLM accounting |
| `cpu_budget.py` | Adaptive worker-pool sizing |
| `pubsub_client.py`, `cloud_dispatch.py` | Cloud dispatch |
| `image_gen.py`, `image_search.py`, `reusable_images.py`, `music_gen.py`, `video_gen.py` | Media integrations |
| `url_fetch.py` | Allowlisted URL fetcher |
| `prompt_history.py` | Stores last N prompt renderings for debugging |

## Chroma

One collection per conversation. `shared.vector_store` handles create / open / upsert / query with per-chunk metadata (page, chapter, file name, section).  
Modes: `CHROMA_MODE=local` (persistent on disk) or `CHROMA_MODE=http`.

## Run locally

```bash
cd python
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in OPENAI_API_KEY etc.

uvicorn server:app --app-dir src --host 0.0.0.0 --port 8321 --reload
```

## Optional: local-llm-pdf-ocr for scanned PDFs

The extractor can use local-llm-pdf-ocr before OpenAI Vision fallback.

1. Clone https://github.com/ahnafnafee/local-llm-pdf-ocr
2. Set environment variables in `python/.env`:

```env
LOCAL_PDF_OCR_ENABLED=true
LOCAL_PDF_OCR_REPO_PATH=/absolute/path/to/local-llm-pdf-ocr
# Optional overrides
# LOCAL_PDF_OCR_TIMEOUT_SEC=180
# LOCAL_PDF_OCR_API_BASE=http://localhost:1234/v1
# LOCAL_PDF_OCR_MODEL=allenai/olmocr-2-7b
# LOCAL_PDF_OCR_GROUNDED=false
```

If local OCR is unavailable, times out, or returns no page text, the pipeline
automatically falls back to the existing OpenAI Vision OCR/description flow.

## Tests & lint

```bash
cd python && source .venv/bin/activate
python -m pytest
ruff check .
ruff format --check .
```

## Live e2e image generation test

Calls the real OpenAI API and saves every streamed partial frame plus the final
image to `e2e/output/` (gitignored) so you can visually inspect generation quality.

```bash
cd python
RUN_REAL_OPENAI_TEST=1 \
  OPENAI_API_KEY=sk-... \
  make e2e
```

Optional env overrides:

| Variable | Default |
|---|---|
| `REAL_OPENAI_IMAGE_TEST_SIZE` | `1024x1536` |
| `REAL_OPENAI_IMAGE_TEST_PROMPT` | quiet dermatology clinic portrait prompt |

After a run, `e2e/output/` contains `partial_0.jpg`, `partial_1.jpg`, `partial_2.jpg`
(progressive quality frames) and `final.jpg` (full-resolution result).
