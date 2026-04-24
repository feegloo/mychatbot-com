# ChatRAG Hybrid RAG App

A production-oriented hybrid RAG application with:

- **Vue 3 + TypeScript** frontend
- **Node.js + Koa + TypeScript** backend
- **Python indexing/query engine** (FastAPI server + shared modules)
- **Chroma** vector store
- **PostgreSQL** for app metadata

## How it works

The web app uploads files to the Node backend. The backend stores files on disk (can be swapped for S3), creates a unique conversation URL, and delegates document indexing to the Python engine.

Python performs:
- file loading and extraction (PDF, DOCX, XLSX, images, plain text)
- paragraph / markdown / heading-aware splitting
- smaller overlapping chunking
- embeddings generation
- vector storage in Chroma (one collection per conversation)
- welcome message generation and suggested questions

The user visits a shareable URL:

- `https://chatrag.app/c/<conversationId>`

and asks questions. The backend calls Python again to retrieve relevant chunks and generate a contextual answer with citations.

## Architecture

```text
frontend (Vue)  →  backend (Koa/TypeScript)  →  python FastAPI engine  →  Chroma
                                  |
                                  v
                              PostgreSQL
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed diagrams.

## Python indexing entry points

The backend calls the Python FastAPI server (`src/server.py`) over HTTP. For local debugging:

```bash
# Index a file directly
python3.11 python/src/index_documents.py \
  --conversation-id <id> \
  --collection-name <collection> \
  --file /absolute/path/file.pdf

# Ask a question directly
python3.11 python/src/answer_question.py \
  --conversation-id <id> \
  --collection-name <collection> \
  --question "What is this document about?"
```

## Supported file types

- PDF
- TXT / MD / CSV / JSON / HTML / XML
- DOCX
- XLS / XLSX
- Images (JPEG, PNG, WebP — with EXIF extraction and optional OCR)

## Quick start

### 1. Install dependencies

#### Frontend
```bash
cd frontend
npm install
```

#### Backend
```bash
cd backend
npm install
```

#### Python
```bash
cd python
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start infrastructure locally

If you have Docker:
```bash
docker compose up -d
```

This starts PostgreSQL and Chroma.

If you do not have Docker:
- run PostgreSQL yourself
- set `CHROMA_MODE=local`
- Python will use local persistent Chroma in `./data/chroma`

### 3. Configure environment

Copy the examples:
```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
cp python/.env.example python/.env
```

### 4. Run database schema

Run the SQL schema from the project root:

```bash
docker exec -i chatrag-postgres psql -U chatrag -d chatrag < backend/sql/schema.sql
```

### 5. Start services

#### Backend
```bash
cd backend
npm run dev
```

#### Frontend
```bash
cd frontend
npm run dev
```

#### Python
Python is called by the backend, so it does not need a long-running server for MVP.

## Testing the Pub/Sub worker locally

By default the backend runs indexing inline (`WORKER_MODE=inline`) — fine for casual dev, but it doesn't exercise the `chatrag-worker` code path that runs in production. To run the full publish → subscribe → index flow on your laptop, use the bundled GCP Pub/Sub emulator:

```bash
# 1. Start emulator + bootstrap topic/subscription (idempotent)
docker compose up -d pubsub-emulator pubsub-init

# 2. Worker (terminal A)
cd python && source .venv/bin/activate
export PUBSUB_EMULATOR_HOST=localhost:8085
export GCP_PROJECT_ID=chatrag-local
export PUBSUB_TOPIC=chatrag-indexing
export PUBSUB_SUBSCRIPTION=chatrag-indexing-sub
python worker_pubsub.py

# 3. Backend (terminal B) — same env + cloud_run mode
cd backend
export PUBSUB_EMULATOR_HOST=localhost:8085
export GCP_PROJECT_ID=chatrag-local
export PUBSUB_TOPIC=chatrag-indexing
export WORKER_MODE=cloud_run
npm run dev
```

Both `@google-cloud/pubsub` (Node) and `google-cloud-pubsub` (Python) auto-detect `PUBSUB_EMULATOR_HOST` — no GCP credentials needed and no code changes between local and prod. Progress events still flow back through the existing `indexing_events` → Postgres NOTIFY → SSE pipeline.

Verify the emulator is healthy:
```bash
curl -sS http://localhost:8085/v1/projects/chatrag-local/topics
curl -sS http://localhost:8085/v1/projects/chatrag-local/subscriptions
```

## Default URLs

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:3000`
- Chroma HTTP: `http://localhost:8000`
- PostgreSQL: `localhost:5432`

## Production deployment options

### GCP
Recommended simple route:
- frontend build served by backend, or deploy frontend separately
- backend on **Cloud Run**
- PostgreSQL on **Cloud SQL**
- file storage on local persistent volume for MVP, later **Cloud Storage**
- optional Chroma on VM / container / private service

Cloud Run supports mapping a custom domain to a service after verifying the domain.

## Domain example: chatrag.app

If you buy the domain on GoDaddy:
1. deploy the app first and get its target hostname / service endpoint
2. add DNS records in GoDaddy that point to the deployed app
3. for GCP Cloud Run, verify the domain and add the mapping records Google gives you.

## Root URL behavior

- `https://chatrag.app/` shows a blank upload page
- once files are uploaded, the app redirects the user to:
  - `https://chatrag.app/c/<conversationId>`

That URL is shareable and reopens the same uploaded knowledge base.

## Notes on Chroma

Chroma collections are the main storage unit — one collection per conversation. Querying the collection is the retrieval step used by the RAG flow. `shared.vector_store` handles create / open / upsert / query.

## Notes on notebook execution

Papermill support has been removed. All indexing now runs through the Python FastAPI server (`src/server.py`) or the one-shot CLI scripts.

# misc

get latest error logs from production:

```
# App errors (Cloud Run)
gcloud logging read 'severity>="ERROR"' --project=chatbotqa-app --limit=2000 --freshness=1h --format='value(timestamp, severity, textPayload)'

# PostgreSQL logs (Cloud SQL)
gcloud logging read 'resource.type="cloudsql_database" AND resource.labels.database_id="chatbotqa-app:chatrag-db-instance" AND log_name="projects/chatbotqa-app/logs/cloudsql.googleapis.com%2Fpostgres.log"' --project=chatbotqa-app --limit=50 --freshness=1h --format='value(timestamp, severity, textPayload)'
```

# remote SQL

install

```
gcloud components install cloud-sql-proxy
```

Option 1: Interactive psql session (simplest)

```
gcloud sql connect chatrag-db-instance --user=chatrag --database=chatrag --project=chatbotqa-app
```

Option 2: One-liner with query piped in

```
echo "SELECT * FROM conversation_messages ORDER BY created_at DESC LIMIT 20;" | \
  gcloud sql connect chatrag-db-instance --user=chatrag --database=chatrag --project=chatbotqa-app
```

Option 3: Load credentials from .env.gcp automatically

```
source infra/cloudrun/.env.gcp && \
  PGPASSWORD="$DB_PASSWORD" gcloud sql connect chatrag-db-instance \
    --user=chatrag --database=chatrag --project="$GCP_PROJECT_ID"
```

Or for a non-interactive query:

```
source infra/cloudrun/.env.gcp && \
  echo "SELECT * FROM conversation_messages ORDER BY created_at DESC LIMIT 20;" | \
  PGPASSWORD="$DB_PASSWORD" gcloud sql connect chatrag-db-instance \
    --user=chatrag --database=chatrag --project="$GCP_PROJECT_ID"
```