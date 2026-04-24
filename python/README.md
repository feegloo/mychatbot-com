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

## Tests & lint

```bash
cd python && source .venv/bin/activate
python -m pytest
ruff check .
ruff format --check .
```
