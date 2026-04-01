# Whole Solution Architecture

This document describes the full hybrid architecture of **MyChatbot**.

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
mychatbot.com
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
https://mychatbot.com/
    -> blank upload page

https://mychatbot.com/c/<conversationId>
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
