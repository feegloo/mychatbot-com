# 🧠 Building ChatRAG — A Production RAG App from Scratch

## How I built a full-stack Retrieval-Augmented Generation application with Python, LangChain, ChromaDB, Vue 3, and Node.js

---

I wanted to build something real with RAG — not a tutorial demo, but a full production application where users upload documents, ask questions, and get answers grounded in their actual content with source citations.

The result is **ChatRAG** ([chatrag.app](https://chatrag.app)) — a web app where you drag-and-drop files and chat with an AI that retrieves relevant passages from your documents to answer questions. Every answer includes citations pointing back to the exact file, page, and section.

In this article, I'll walk through the architecture, the RAG pipeline, the key design decisions, and the technical details that make it work.

---

## 🏗️ Architecture Overview

ChatRAG is a hybrid Python + Node.js application with three main layers:

```
┌─────────────────────────────────────────────────────┐
│                    Frontend                          │
│              Vue 3 + TypeScript + Vite               │
│                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Upload   │  │ Conversation │  │  Chat Message  │  │
│  │   Page    │  │    Page      │  │  + Citations   │  │
│  └──────────┘  └──────────────┘  └───────────────┘  │
└──────────────────────┬──────────────────────────────┘
                       │ REST API + SSE
┌──────────────────────▼──────────────────────────────┐
│                    Backend                           │
│           Node.js + Koa + TypeScript                 │
│                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Upload   │  │Conversations │  │  Ask / Stream  │  │
│  │  Routes   │  │   Routes     │  │   Routes       │  │
│  └──────────┘  └──────────────┘  └───────────────┘  │
│                       │                              │
│              ┌────────▼────────┐                     │
│              │  Python Runner  │                     │
│              │ (spawn process) │                     │
│              └────────┬────────┘                     │
└───────────────────────┼─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│                 Python AI Engine                     │
│            LangChain + OpenAI + Anthropic            │
│                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │Extractors│  │   Chunkers   │  │  RAG Pipeline  │  │
│  │(PDF,DOCX │  │ (Structured  │  │ (Embed→Query  │  │
│  │ XLS,CSV) │  │  + Token)    │  │  →LLM→Answer) │  │
│  └──────────┘  └──────────────┘  └───────────────┘  │
└────────┬───────────────────────────────┬────────────┘
         │                               │
┌────────▼────────┐            ┌─────────▼─────────┐
│   PostgreSQL    │            │     ChromaDB       │
│   (metadata,    │            │  (vector embeddings│
│    messages,    │            │   per conversation)│
│    access)      │            │                    │
└─────────────────┘            └────────────────────┘
```

### Why This Hybrid Architecture?

Python is the natural choice for the AI/ML layer — LangChain, OpenAI SDKs, document parsers are all Python-first. But for the web layer, Node.js with Koa gives us a lightweight, non-blocking server that handles file uploads, SSE streaming, and API routing efficiently.

The backend spawns Python scripts as child processes for indexing and answering. Each script outputs structured JSON to stdout, which the Node.js backend parses. This clean separation means:

- The Python engine can be developed and tested independently
- The backend doesn't need Python bindings — just process spawning
- Logs from indexing and non-streaming answer script executions are saved to timestamped files for debugging, while the streaming path currently logs to stdout/stderr

---

## 📄 The Upload Screen

The first thing users see is a clean drag-and-drop upload zone. You select files (or drag them in), and hit upload.

![Conversation screen with uploaded files and chat](https://github.com/user-attachments/assets/1149d32c-6398-400e-a775-0e9c7cb0aa3d)

**Supported file formats:**
- **PDF** — extracted page by page with `pypdf`, with PDF text reflow to join soft-wrapped lines
- **DOCX** — parsed with `docx2txt`
- **Excel (XLS/XLSX)** — all sheets read with `pandas` and exported as CSV-formatted text
- **CSV** — read as-is
- **JSON** — pretty-printed for readability
- **HTML, XML, YAML, Markdown, TXT, RTF** — read as plain text

When you upload, the backend:
1. Creates a conversation with a unique UUID
2. Derives an owner token using SHA-256 (from the conversation ID + a random salt)
3. Stores files on disk
4. Spawns the Python indexer in the background
5. Returns a shareable URL: `chatrag.app/c/<conversationId>`

The frontend saves the owner token in `localStorage` and redirects to the conversation page while indexing runs in the background.

---

## 🔪 The Indexing Pipeline — From Files to Vectors

This is where the RAG magic happens. The Python indexer takes raw files and converts them into searchable vector embeddings.

```
┌─────────────┐     ┌───────────────┐     ┌──────────────────┐
│   Raw Files  │────▶│  Text         │────▶│  Structured      │
│  (PDF, DOCX, │     │  Extraction   │     │  Split           │
│   XLS, CSV)  │     │  + Sanitize   │     │  (paragraphs,    │
└─────────────┘     └───────────────┘     │   markdown)      │
                                           └────────┬─────────┘
                                                    │
                    ┌───────────────┐     ┌─────────▼─────────┐
                    │  ChromaDB     │◀────│  Token-Aware      │
                    │  Collection   │     │  Chunk Split      │
                    │  (embeddings) │     │  (≤1600 chars,    │
                    └───────────────┘     │   200 overlap)    │
                                          └───────────────────┘
                                                    │
                                          ┌─────────▼─────────┐
                                          │  Suggested        │
                                          │  Questions        │
                                          │  (4 AI-generated) │
                                          └───────────────────┘
```

### Stage 1: Text Extraction

Each file format has a dedicated extractor. The PDF extractor deserves special mention — it doesn't just dump raw text. It:

- Extracts text **page by page**, adding `# Page N` headers for context
- **Reflows text** — PDFs break lines at arbitrary points due to layout; the extractor joins soft-wrapped lines (single `\n`) back into flowing paragraphs while preserving real paragraph breaks (double `\n`)
- **Sanitizes** output — removes null characters and control characters that would break JSON/database storage

```python
def extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: List[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = _reflow_pdf_text(text.strip())
        parts.append(f"# Page {page_number}\n\n{text}")
    return _sanitize_text("\n\n".join(parts).strip())
```

### Stage 2: Structured Splitting

Before chunking for embeddings, the text is split into logical units:

1. **Markdown detection** — if the text contains headers (`#`, `##`, `###`), use LangChain's `MarkdownHeaderTextSplitter` to split by sections
2. **Paragraph splitting** — for plain text, split on double newlines (`\n\n`) to preserve natural document structure
3. **Section header detection** — single-line text that starts with an uppercase letter and doesn't end with punctuation is tagged as a header

Each resulting document carries metadata: `is_header`, `header` text, and eventually `section`, `page`, and `file_name`.

### Stage 3: Token-Aware Chunking

Now the structured segments get chunked for embedding:

- **Small paragraphs (≤1600 chars)** — kept as-is. Each becomes one embedding vector.
- **Large paragraphs (>1600 chars)** — recursively split using LangChain's `RecursiveCharacterTextSplitter` with `["\n\n", "\n", ". ", " ", ""]` separators and 200-character overlap.

This two-stage approach was a key improvement. Originally, I embedded entire files as single chunks — terrible for retrieval precision. After implementing structured + token-aware splitting, a file that was 1 chunk became 10+ semantic chunks. Queries about specific topics now retrieve only the relevant sections.

### Stage 4: Vector Embedding & Storage

Each chunk is embedded using **OpenAI's `text-embedding-3-small`** model and stored in **ChromaDB** — an open-source vector database. Every conversation gets its own Chroma collection, providing complete isolation.

```python
def upsert_chunks(collection_name, conversation_id, chunks):
    collection = client.get_or_create_collection(name=collection_name)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    vectors = embeddings.embed_documents([chunk.text for chunk in chunks])
    
    collection.add(
        ids=[chunk.chunk_id for chunk in chunks],
        documents=[chunk.text for chunk in chunks],
        embeddings=vectors,
        metadatas=[{
            "conversation_id": conversation_id,
            "file_name": chunk.file_name,
            "section": chunk.section or "",
            "page": chunk.page if chunk.page is not None else -1,
        } for chunk in chunks],
    )
```

### 💡 Stage 5: Suggested Questions

After indexing, the system generates **4 starter questions** using LLM-powered question generation. It uses **stratified sampling** — taking chunks from the beginning, middle, and end of the document to cover diverse topics.

The prompt is **language-aware**: if the documents are in Polish, the questions are generated in Polish. Language detection uses the `langdetect` library on the first 2000 characters of content.

---

## 💬 The Conversation Screen

Once indexing completes, you land on the conversation page. The layout:

- **Left sidebar** — lists all your conversations with status indicators (yellow pulse = processing, red = failed)
- **Right sidebar** — shows uploaded files as pills, suggested questions as clickable buttons, and (for owners) incoming access requests
- **Center panel** — the chat interface with user/assistant messages

### 💡 Suggested Questions

The AI-generated questions appear as clickable pills in the sidebar. Click one, and it's sent as your first question. This solves the "blank page" problem — users always know what to ask their documents.

![Suggested questions on mobile — clickable AI-generated prompts](https://github.com/user-attachments/assets/48ac4cca-8b65-4a9d-80cf-3efa0bfc84b6)

### 📚 Chat with Citations

When you ask a question, the system:
1. Embeds your question using the same OpenAI embedding model
2. Queries ChromaDB for the top-4 most relevant chunks (filtered by conversation)
3. Builds a context string with file names, sections, and page numbers
4. Feeds the context + question to the LLM (Anthropic Claude or OpenAI GPT)
5. Returns the answer with citations

Each citation shows:
- **File name** — which document the answer came from
- **Section** — the header or first line of the relevant chunk
- **Page number** — for PDFs, the exact page
- **Source text** — the actual passage used

The frontend renders citations as **tabs** — click different source tabs to see which passages informed each part of the answer.

---

## 🤖 The RAG Pipeline — How Answers Are Generated

```
┌──────────┐    ┌───────────────┐    ┌─────────────────┐
│  User's   │───▶│   Embed       │───▶│  Query ChromaDB │
│  Question │    │   Question    │    │  (top-4 chunks, │
└──────────┘    └───────────────┘    │   L2 distance)  │
                                      └────────┬────────┘
                                               │
┌──────────────────────────────────────────────▼────────┐
│                    Build Context                       │
│  [Source 1] File: report.pdf | Page: 3                │
│  "The quarterly revenue increased by 15%..."          │
│  ---                                                   │
│  [Source 2] File: analysis.docx | Section: Summary    │
│  "Key findings indicate a positive trend..."          │
└──────────────────────────┬────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │     LLM Chain           │
              │  Prompt → LLM → Parser  │
              │                         │
              │  "You are a helpful RAG  │
              │   assistant. Answer      │
              │   using ONLY the         │
              │   retrieved context..."  │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │   Answer + Citations    │
              │   (grounded in sources) │
              └─────────────────────────┘
```

### 🔎 Distance Thresholding

Not all retrieved chunks are relevant. The system applies **adaptive distance thresholds** based on question length:

| Question words | Max L2 distance | Rationale |
|---|---|---|
| 1 word | 1.5 | Single-word queries are broad; allow wider matches |
| 2 words | 1.3 | Slightly stricter |
| 3+ words | 1.1 | Specific queries should match closely |

This prevents the LLM from seeing irrelevant context and hallucinating connections.

### 🤖 LLM Provider Flexibility

The system supports both **OpenAI** and **Anthropic (Claude 3.5 Haiku)**. The OpenAI chat model is configurable via environment settings (`OPENAI_CHAT_MODEL`); in the current backend configuration, it defaults to `gpt-4.1-mini`. The default provider is Anthropic with automatic fallback to OpenAI if the Anthropic API key isn't configured. Temperature is set to 0 for deterministic, factual responses.

```python
def get_llm():
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        return ChatAnthropic(
            model=settings.anthropic_chat_model,
            temperature=0,
        )
    else:
        return ChatOpenAI(
            model=settings.openai_chat_model,
            temperature=0,
        )
```

### ⚡ Real-Time Streaming

For a better UX, answers stream word-by-word using **Server-Sent Events (SSE)**:

1. Frontend opens an SSE connection to `GET /api/stream-answer`
2. Backend spawns `stream_answer.py`
3. Python iterates over `chain.stream()` and yields each token
4. Backend relays tokens to the frontend in real-time
5. After streaming completes, citations are sent as a final event

![Streaming response with typing indicator](https://github.com/user-attachments/assets/78306093-91b5-4ca9-8069-3ee3cd9e9f19)

```
event: token
data: {"token": "The"}

event: token
data: {"token": " quarterly"}

event: token
data: {"token": " revenue"}

...

event: citations
data: {"citations": [{"fileName": "report.pdf", "page": 3, ...}]}

event: done
data: {}
```

---

## 🔒 Access Control & Sharing

Every conversation has a unique, shareable URL. The access model has three roles:

| Role | Can chat | Can upload files | Can approve access |
|---|---|---|---|
| **Owner** | ✅ | ✅ | ✅ |
| **Editor** | ✅ | ✅ | ❌ |
| **Viewer** | ✅ | ❌ | ❌ |

### How Tokens Work

Security is token-based with **deterministic derivation**:

```
Owner token  = SHA-256(conversationId + ":" + salt)
Editor token = SHA-256(conversationId + ":" + salt + ":editor")
```

The salt is a random UUID stored in the database. Clients never see the salt — only the derived token (sent as `x-conversation-token` header). Derived tokens are stored in the `conversation_access_tokens` table and validated via DB lookup. This means:
- Tokens are deterministically derived from the salt, so they can be re-generated if needed
- Validation queries the `conversation_access_tokens` table by conversation ID and token
- Owner and editor tokens are mathematically distinct

### Access Request Workflow

When someone opens a shared conversation link:
1. They become a **Viewer** — can chat, but not upload
2. They can click **"Request access"** with their name
3. The **Owner** sees the request in their sidebar
4. Owner clicks **"Approve"** → the system derives an editor token
5. Viewer polls for approval, gets the editor token, saves to `localStorage`
6. Now they're an **Editor** and can upload more files

---

## 🐘 Database Schema

PostgreSQL stores all metadata and conversation state:

```sql
conversations                -- id, salt, display_name, status, vector_collection_name, storage_namespace
uploaded_files               -- file metadata per conversation (original_name, stored_name, mime_type, size_bytes)
suggested_questions          -- AI-generated starter questions
conversation_messages        -- full chat history with citations_json (JSONB)
conversation_access_tokens   -- derived tokens with roles (owner/editor)
access_requests              -- pending/approved access requests with editor_token
```

The `conversation_messages` table stores citations as `citations_json` (JSONB), preserving the full structure (file name, section, page, chunk text) alongside each assistant response.

---

## 🐳 Deployment

The app is containerized with a **multi-stage Dockerfile**:

1. **Stage 1**: Build Vue frontend with Vite → static assets
2. **Stage 2**: Compile TypeScript backend → JavaScript
3. **Stage 3**: Production image with Node 22 + Python 3 virtualenv

```dockerfile
# Production stage
FROM node:22-slim
RUN apt-get update && apt-get install -y python3 python3-venv
# ... setup Python venv, install requirements
# ... copy compiled backend + frontend dist
EXPOSE 8080
CMD ["node", "dist/index.js"]
```

### ☁️ Cloud Deployment Options

**GCP Cloud Run** (~$7/mo for demo):
- Auto-scales 0→3 instances
- Cloud SQL for PostgreSQL (db-f1-micro)
- Free SSL with domain mapping

**AWS App Runner** (~$18/mo for demo):
- Auto-pause for cost savings
- RDS for PostgreSQL (db.t4g.micro)
- Route 53 for DNS

Both options deploy via simple scripts (`deploy-gcp.sh` / `deploy-aws.sh`). GCP deployment integrates with GitHub Actions for CI/CD; AWS deploys via the CLI script.

---

## 🛠️ Tech Stack Summary

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | Vue 3, TypeScript, Vite | SPA with reactive UI |
| Backend | Node.js, Koa, TypeScript | API server, file handling, SSE streaming |
| AI Engine | Python, LangChain | RAG orchestration, document processing |
| LLM | OpenAI GPT-4o-mini, Anthropic Claude 3.5 Haiku | Answer generation |
| Embeddings | OpenAI text-embedding-3-small | Semantic vector encoding |
| Vector DB | ChromaDB | Similarity search, per-conversation collections |
| Metadata DB | PostgreSQL | Conversations, messages, access control |
| Deployment | Docker, GCP Cloud Run, AWS App Runner | Containerized cloud hosting |
| Testing | Vitest (JS), Pytest (Python), Playwright (E2E) | Full test coverage |

---

## 🎯 Key Takeaways

**1. Two-stage text splitting is critical.** Single-chunk-per-file embeddings produce terrible retrieval results. Structured splitting (paragraph/markdown-aware) followed by token-aware chunking dramatically improved precision.

**2. Adaptive distance thresholds improve answer quality.** Short queries need wider matching; specific queries need tighter thresholds. One-size-fits-all doesn't work.

**3. Hybrid architectures work well.** Python for AI/ML + Node.js for web is a natural split. Process spawning is simple, reliable, and keeps concerns separated.

**4. Per-conversation isolation simplifies everything.** Each conversation gets its own Chroma collection. No cross-contamination, easy cleanup, simple queries.

**5. Streaming transforms the UX.** Showing tokens as they arrive (via SSE) makes the app feel responsive even when LLM inference takes seconds.

**6. Citation transparency builds trust.** Users can verify every answer by clicking through to the source passage. This is what separates a useful RAG app from a chatbot wrapper.

---

Try it at [chatrag.app](https://chatrag.app) — upload any document and start chatting.

The full source is on [GitHub](https://github.com/feegloo/chatrag-app).

---

<!-- Tags for Medium publishing: RAG, LangChain, Python, AI, Full-Stack Development -->
