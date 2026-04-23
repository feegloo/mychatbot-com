# Whole Solution Architecture

This document describes the full hybrid architecture of **ChatRAG**.

## Overview

The system is split into 3 main parts:

- **Frontend** - Vue 3 + TypeScript
- **Backend** - Node.js + Koa + TypeScript
- **Python AI Engine** - LangChain + notebook/scripts
- **Vector DB** - Chroma
- **Metadata DB** - PostgreSQL

## High-level diagram

```text
                ┌───────────────────────┐
                │       Frontend        │
                │   Vue 3 + TypeScript  │
                │                       │
                │ - upload files        │
                │ - chat UI             │
                │ - suggested questions │
                │ - role actions        │
                └──────────┬────────────┘
                           │ HTTP / SSE
                           ▼
                ┌───────────────────────┐
                │       Backend         │
                │   Node.js + Koa       │
                │                       │
                │ - upload endpoints    │
                │ - chat endpoints      │
                │ - access requests     │
                │ - role validation     │
                │ - storage             │
                │ - Python orchestration│
                └──────────┬────────────┘
                           │ spawn / call
                           ▼
                ┌───────────────────────┐
                │        Python         │
                │  LangChain + Notebook │
                │                       │
                │ - extract text        │
                │ - split/chunk         │
                │ - embeddings          │
                │ - RAG answering       │
                └──────────┬────────────┘
                           │
                           ▼
                ┌───────────────────────┐
                │      Vector DB        │
                │        Chroma         │
                │                       │
                │ - embeddings          │
                │ - chunk metadata      │
                │ - semantic retrieval  │
                └───────────────────────┘
```

## Upload flow

```text
User
  │
  ▼
Frontend upload form
  │
  ▼
POST /upload
  │
  ▼
Backend
  - create conversationId
  - assign owner token
  - store files on disk
  │
  ▼
Python indexer
  - load uploaded files
  - extract text
  - split into chunks
  - generate embeddings
  - save vectors to Chroma
  - generate suggested questions
  │
  ▼
Backend marks conversation READY
  │
  ▼
Frontend redirects to /c/<conversationId>
```

## CPU budget & worker delegation

The main `chatrag` service caps its own indexing CPU usage at 50% of
system cores (always leaving ≥1 CPU for HTTP traffic). When a new upload
would exceed that budget, the job is published to a GCP Pub/Sub topic
and picked up by `chatrag-worker` — a lightweight Python-only Cloud Run
service that subscribes to the topic.

```text
chatrag (main)
  ├─ small file + budget free → process inline
  └─ large file OR budget full → publish to chatrag-indexing topic
                                            │
                                            ▼
                                  chatrag-worker (warm, min=1)
                                  - pulls JSON job payload
                                  - downloads PDF (local or gs://)
                                  - runs index_documents()
                                  - emits progress to indexing_events
                                            │
                                            ▼
                                  Backend SSE relay → browser
```

Per-file CPU slot allocation (1 or 2):
- `<5MB AND <50 pages` → 1 slot
- otherwise → 2 slots

Job payload (`python/shared/pubsub_client.py::IndexingJobPayload`):
```json
{
  "workerName": "chatrag-001",
  "fileName": ["/local/path.pdf", "gs://bucket/key.pdf"],
  "conversationId": "...",
  "collectionName": "...",
  "jobId": "uuid",
  "metadata": {"uploadedFileNames": [...], "storedToOriginal": {...}}
}
```

`workerName` is advisory — any worker on the shared subscription may
consume the message. Pub/Sub provides retry + dead-letter; the
`indexing_events` Postgres table remains the source of truth for
progress events streamed back to the browser.

## Add-more-files flow

```text
Owner / Editor
  │
  ▼
POST /conversations/:id/files
  │
  ▼
Backend validates owner/editor token
  │
  ▼
Store new files
  │
  ▼
Python re-indexes only new files
  │
  ▼
Chroma collection grows
  │
  ▼
Future questions search across larger context
```

## Chat flow

```text
User asks question
  │
  ▼
POST /ask
  │
  ▼
Backend calls Python answerer
  │
  ▼
Python
  - embed question
  - query Chroma
  - build context
  - call LLM
  - return answer + citations
  │
  ▼
Frontend renders answer
```

## Roles

### Owner
- created the conversation by first upload
- can upload more files
- can approve editor requests

### Editor
- approved by owner
- can upload more files
- can expand context for the same conversation

### Viewer
- can open shared link
- can chat
- can request upload access

## Storage model

### Disk
```text
/storage/<conversationId>/<uuid>_original_file_name.pdf
```

### Chroma metadata
```text
conversation_id
file_name
chunk_id
section
page
text
embedding
```

### PostgreSQL
- conversations
- uploaded_files
- suggested_questions
- conversation_access_tokens
- access_requests

## Deployment shape

```text
chatrag.app
   │
   ▼
Frontend
   │
   ▼
Backend API
   │
   ├── PostgreSQL
   ├── Chroma
   └── Python engine
```

## Root URL behavior

```text
https://chatrag.app/
    -> blank upload page

https://chatrag.app/c/<conversationId>
    -> shareable conversation page
```

## Key idea

```text
Uploaded files
   ↓
Text extraction
   ↓
Chunking
   ↓
Embeddings
   ↓
Vector search
   ↓
LLM answer with citations
```
