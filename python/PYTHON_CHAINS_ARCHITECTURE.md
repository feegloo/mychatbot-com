# Python Chains Architecture

This document focuses on how the Python side is connected with LangChain.

## Core concept

A chain is a pipeline where output from one component becomes input to the next.

Basic shape:

```text
input -> prompt -> LLM -> output parser -> output
```

In code:

```python
chain = prompt | chat | parser
```

## Simple correction / transformation chain

```text
          ┌──────────────┐
input →   │ Prompt       │
          └──────┬───────┘
                 │
                 ▼
          ┌──────────────┐
          │ LLM (Chat)   │
          └──────┬───────┘
                 │
                 ▼
          ┌──────────────┐
          │ OutputParser │
          └──────┬───────┘
                 │
                 ▼
              output
```

## Indexing pipeline

This is not one single LangChain chain. It is a processing pipeline:

```text
[Uploaded files]
   │
   ▼
[Text extractors]
   - PDF
   - DOCX
   - XLS/XLSX
   - TXT / MD / JSON / HTML
   │
   ▼
[Structure-aware split]
   - markdown headers (#, ##, ###)
   - fallback: paragraphs
   │
   ▼
[Smaller chunk split]
   - recursive/token-like split
   - overlap
   │
   ▼
[Embedding model]
   - OpenAI embeddings
   │
   ▼
[Chroma collection]
```

## Question-answering RAG pipeline

```text
[User question]
   │
   ▼
[Embed question]
   │
   ▼
[Query Chroma]
   │
   ▼
[Top-k chunks]
   │
   ▼
[Context builder]
   │
   ▼
[Prompt template]
   │
   ▼
[LLM]
   │
   ▼
[Output parser]
   │
   ▼
[Answer + citations]
```

## Box view of the RAG answer chain

```text
           ┌────────────────────────┐
input  →   │ User question          │
           └─────────┬──────────────┘
                     │
                     ▼
           ┌────────────────────────┐
           │ Question embedding     │
           └─────────┬──────────────┘
                     │
                     ▼
           ┌────────────────────────┐
           │ Chroma retrieval       │
           │ (semantic search)      │
           └─────────┬──────────────┘
                     │
                     ▼
           ┌────────────────────────┐
           │ Context builder        │
           │ merges chunks + meta   │
           └─────────┬──────────────┘
                     │
                     ▼
           ┌────────────────────────┐
           │ Prompt template        │
           │ question + context     │
           └─────────┬──────────────┘
                     │
                     ▼
           ┌────────────────────────┐
           │ Chat LLM               │
           └─────────┬──────────────┘
                     │
                     ▼
           ┌────────────────────────┐
           │ StrOutputParser        │
           └─────────┬──────────────┘
                     │
                     ▼
           ┌────────────────────────┐
           │ final answer           │
           └────────────────────────┘
```

## Prompt composition idea

The prompt is built from:
- the **question**
- the **retrieved context**
- instructions such as:
  - answer only from context
  - do not invent missing facts
  - keep answer concise
  - include citations

Conceptually:

```text
Prompt =
  system instructions
+ user question
+ retrieved chunks
```

## Suggested-question generation chain

After indexing, the system can also run another chain:

```text
[Sample chunks]
   │
   ▼
[Question generation prompt]
   │
   ▼
[LLM]
   │
   ▼
[Parser]
   │
   ▼
[3-4 clickable suggested questions]
```

## Runtime

Node backend calls the persistent Python FastAPI `server.py` over HTTP; `server.py` dispatches to the `shared/` LangChain + Chroma logic. For GCP, large indexing jobs are also pulled by `worker_pubsub.py` from Pub/Sub.

## Summary

The Python side has two responsibilities:

### 1. Indexing
```text
files -> text -> chunks -> embeddings -> Chroma
```

### 2. Answering
```text
question -> retrieval -> prompt -> LLM -> answer
```

That is the core LangChain/RAG mental model for this project.
