# LinkedIn Post — ChatRAG Launch

I want to share with you **chatrag.app** — an AI-powered app I built from scratch.

You upload your files (PDFs, Word docs, spreadsheets, CSVs, and more), and a chatbot answers your questions using **Retrieval-Augmented Generation (RAG)**. In short, it lets you ask semantic questions over your uploaded sources — like chatting with the person who wrote the documents.

## How it works under the hood

The AI engine is built in **Python** with **LangChain** orchestrating the full RAG pipeline. When you upload documents, they go through intelligent text splitting (with language-aware chunking), get embedded, and are stored in **ChromaDB** — an open-source vector database. Each conversation gets its own isolated vector collection, so your data stays clean and scoped.

When you ask a question, the system performs a semantic similarity search over your documents, retrieves the most relevant chunks, and feeds them as context to the LLM. The answer comes back grounded in your actual sources — with citations — not hallucinated from general training data.

## The tech stack

- 🐍 **Python** + **LangChain** — RAG pipeline, document processing, and LLM orchestration
- 🧠 **OpenAI & Anthropic** — LLM providers (GPT and Claude) for generating answers
- 🗄️ **ChromaDB** — vector database for semantic search and document embeddings
- 🖥️ **Vue 3** + **TypeScript** — modern, reactive frontend
- ⚙️ **Node.js** + **Koa** + **TypeScript** — lightweight backend API
- 🐘 **PostgreSQL** — metadata and conversation storage
- 🐳 **Docker** — containerized deployment on **GCP Cloud Run** and **AWS**

## What makes it interesting

- **Multi-format support**: Upload PDFs, DOCX, Excel, CSV, JSON, HTML, XML, Markdown, and plain text files
- **Shareable conversations**: Every chat session has a unique URL you can share with anyone
- **Suggested questions**: After indexing your documents, the system generates smart starter questions so you know what to ask
- **Language detection**: Automatically detects the language of your documents and responds accordingly
- **Citation-backed answers**: Every response references the specific source passages it drew from

I built this to explore the full lifecycle of a production RAG application — from document ingestion and vector indexing to real-time retrieval and LLM-powered answers. It's been a great deep-dive into the intersection of NLP, information retrieval, and modern web development.

Check it out 👉 https://chatrag.app

#AI #RAG #LangChain #Python #ChromaDB #MachineLearning #NLP #VectorDatabase #OpenAI #Anthropic #Vue3 #TypeScript #NodeJS #FullStack #WebDev #BuildInPublic
