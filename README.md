# ChatRAG Hybrid RAG App

A production-oriented hybrid RAG application with:

- **Vue 3 + TypeScript** frontend
- **Node.js + Koa + TypeScript** backend
- **Python indexing/query engine**
- **Chroma** vector store
- **PostgreSQL** for app metadata
- **Option A:** parameterized Jupyter notebook execution via **Papermill**
- **Option B:** normal Python scripts reusing the same shared logic

## Main idea

The web app uploads files to the Node backend. The backend stores files on disk (with an abstraction that can later switch to S3), creates a unique conversation URL, and then delegates document indexing to Python.

Python performs:
- file loading and extraction
- paragraph / markdown / heading-aware splitting
- smaller overlapping chunking
- embeddings generation
- vector storage in Chroma
- optional suggested questions generation

The user later visits a shareable URL like:

- `https://chatrag.app/c/<conversationId>`

and asks questions. The backend calls Python again to retrieve relevant chunks and generate a contextual answer with citations.

## Architecture

```text
frontend (Vue)  ->  backend (Koa/TypeScript)  ->  python engine  ->  Chroma
                                  |
                                  v
                              PostgreSQL
```

## Two indexing modes

### Option A - keep notebook
Node calls:

```bash
python python/run_notebook_indexer.py   --conversation-id <id>   --collection-name <collection>   --file /absolute/path/file1.pdf   --file /absolute/path/file2.docx
```

This runs a parameterized notebook using Papermill.

### Option B - normal Python scripts
Node calls:

```bash
python python/index_documents.py   --conversation-id <id>   --collection-name <collection>   --file /absolute/path/file1.pdf   --file /absolute/path/file2.docx
```

This is the recommended production runtime.

## Supported file types today

- PDF
- TXT / MD / CSV / JSON / HTML / XML
- DOCX
- XLS / XLSX
- generic text-ish files

## Future extension

- images
- OCR
- audio/video transcripts
- S3 / GCS storage
- websocket streaming
- auth / multi-tenant access control

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

This starts PostgreSQL, Chroma, and Ollama (for local Gemma 4 model).

Ollama auto-pulls `gemma4:e2b` on first start. To use a different model:
```bash
OLLAMA_MODEL=gemma4:26b docker compose up -d
```

To manually pull a model:
```bash
docker exec chatrag-ollama ollama pull gemma4:e2b
```

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

Run the SQL in:
- `backend/sql/schema.sql`

```
cat /Users/{your_user_name}/Downloads/chatrag-hybrid-app/backend/sql/schema.sql \
  | docker exec -i chatrag-postgres psql -U chatrag -d chatrag
```

replace {your_user_name} with your user account name (like 'olek'):

```
cat /Users/olek/Downloads/chatrag-hybrid-app/backend/sql/schema.sql \
  | docker exec -i chatrag-postgres psql -U chatrag -d chatrag
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

## Default URLs

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:3000`
- Chroma HTTP: `http://localhost:8000`
- Ollama (Gemma 4): `http://localhost:11434`
- PostgreSQL: `localhost:5432`

## Local Gemma 4 (offline LLM)

The app can use a local Gemma 4 model via Ollama instead of OpenAI/Anthropic for answering questions. Embeddings still use OpenAI regardless.

### Setup
```bash
# Start all services (Ollama auto-pulls gemma4:e2b on first boot)
docker compose up -d

# Or manually pull a specific model variant
docker exec chatrag-ollama ollama pull gemma4:e2b
```

### Enable in `python/.env`
```
USE_GEMMA=true
GEMMA_MODEL=gemma4:e2b
GEMMA_BASE_URL=http://localhost:11434
```

### Available model variants
| Model | Size | Notes |
|-------|------|-------|
| `gemma4:e2b` | 7.2 GB | Lightest, good for testing |
| `gemma4` (e4b) | 9.6 GB | Default Ollama tag |
| `gemma4:26b` | 18 GB | MoE, fastest throughput (needs GPU VRAM) |
| `gemma4:31b` | 20 GB | Dense, best quality |

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

## Notes on notebook execution

Papermill supports parameterizing notebooks using a cell tagged `parameters`, then executing them with injected values.

## Notes on Chroma

Chroma collections are the main storage unit, and querying collections is the retrieval step used by the RAG flow.

# misc

get latest error logs from production:

```
# App errors (Cloud Run)
gcloud logging read 'severity>="ERROR"' --project=chatbotqa-app --limit=50 --freshness=1h --format='value(timestamp, severity, textPayload)'

# PostgreSQL logs (Cloud SQL)
gcloud logging read 'resource.type="cloudsql_database" AND resource.labels.database_id="chatbotqa-app:chatrag-db-instance" AND log_name="projects/chatbotqa-app/logs/cloudsql.googleapis.com%2Fpostgres.log"' --project=chatbotqa-app --limit=50 --freshness=1h --format='value(timestamp, severity, textPayload)'
```