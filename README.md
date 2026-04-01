# MyChatbot Hybrid RAG App

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

- `https://mychatbot.com/c/<conversationId>`

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
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start infrastructure locally

If you have Docker:
```bash
docker compose up -d postgres chroma
```

If you do not have Docker:
- run PostgreSQL yourself
- set `CHROMA_MODE=local`
- Python will use local persistent Chroma in `./data/chroma`

### 3. Configure environment

Copy the examples:
```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
cp python/.env.example python/.env
```

### 4. Run database schema

Run the SQL in:
- `backend/sql/schema.sql`

```
cat /Users/{your_user_name}/Downloads/mychatbot-hybrid-app/backend/sql/schema.sql \
  | docker exec -i mychatbot-postgres psql -U mychatbot -d mychatbot
```

replace {your_user_name} with your user account name (like 'olek'):

```
cat /Users/olek/Downloads/mychatbot-hybrid-app/backend/sql/schema.sql \
  | docker exec -i mychatbot-postgres psql -U mychatbot -d mychatbot
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
- PostgreSQL: `localhost:5432`

## Production deployment options

### GCP
Recommended simple route:
- frontend build served by backend, or deploy frontend separately
- backend on **Cloud Run**
- PostgreSQL on **Cloud SQL**
- file storage on local persistent volume for MVP, later **Cloud Storage**
- optional Chroma on VM / container / private service

Cloud Run supports mapping a custom domain to a service after verifying the domain. citeturn966466search2turn966466search14

### AWS
Recommended simple route:
- backend on ECS/Fargate or App Runner
- PostgreSQL on RDS
- files on EBS for MVP, later S3
- Route 53 / registrar DNS points the domain to your load balancer or AWS service

Route 53 can route traffic to AWS resources, including load balancers, and alias records can point the root domain to an ELB target. citeturn966466search11turn966466search15

## Domain example: mychatbot.com

If you buy the domain on GoDaddy:
1. deploy the app first and get its target hostname / service endpoint
2. add DNS records in GoDaddy that point to the deployed app
3. for GCP Cloud Run, verify the domain and add the mapping records Google gives you. citeturn966466search2turn966466search18
4. for AWS, point DNS to the service / load balancer, often using Route 53 alias records if you manage DNS in AWS. citeturn966466search11turn966466search15

## Root URL behavior

- `https://mychatbot.com/` shows a blank upload page
- once files are uploaded, the app redirects the user to:
  - `https://mychatbot.com/c/<conversationId>`

That URL is shareable and reopens the same uploaded knowledge base.

## Notes on notebook execution

Papermill supports parameterizing notebooks using a cell tagged `parameters`, then executing them with injected values. citeturn966466search0turn966466search4

## Notes on Chroma

Chroma collections are the main storage unit, and querying collections is the retrieval step used by the RAG flow. citeturn966466search1turn966466search13turn966466search17
