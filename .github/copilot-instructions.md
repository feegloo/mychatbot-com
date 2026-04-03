# Copilot Workspace Instructions for MyChatbot Hybrid RAG App

## Purpose
These instructions guide AI agents (like GitHub Copilot) to be productive and consistent in the MyChatbot Hybrid RAG App workspace. They summarize architecture, conventions, and key workflows, and link to detailed docs where needed.

---

## Architecture Overview
- **Frontend:** Vue 3 + TypeScript ([frontend/](frontend/))
- **Backend:** Node.js + Koa + TypeScript ([backend/](backend/))
- **Python AI Engine:** LangChain, Jupyter notebooks, and scripts ([python/](python/))
- **Vector DB:** Chroma
- **Metadata DB:** PostgreSQL
- See [ARCHITECTURE.md](ARCHITECTURE.md) for diagrams and details.

---

## Build & Test Commands
- **Frontend:**
  - Install: `cd frontend && npm install`
  - Dev: `npm run dev`
  - Test: `npm run test` or `npm run test:unit`
- **Backend:**
  - Install: `cd backend && npm install`
  - Dev: `npm run dev`
  - Test: `npm run test` or `npm run test:unit`
- **Python:**
  - Install: `cd python && pip install -r requirements.txt`
  - Index: `python index_documents.py ...`
  - Answer: `python answer_question.py ...`
  - See [python/README.md](python/README.md) for notebook and script usage.

---

## Key Conventions
- **Link, don’t embed:** Reference docs like [ARCHITECTURE.md](ARCHITECTURE.md) and [python/README.md](python/README.md) instead of duplicating content.
- **Indexing:** Use Python scripts for production, notebooks for experimentation.
- **File Uploads:** Handled by backend, stored on disk (can be swapped for S3).
- **Vector Store:** Chroma collections are per conversation.
- **Shareable URLs:** Format: `/c/<conversationId>`

---

## Potential Pitfalls
- Ensure Python and Node environments are set up before running scripts.
- Chroma and PostgreSQL must be running for full functionality (see docker-compose.yml).
- For cloud deploy, see [infra/aws/README.md](infra/aws/README.md) and [infra/cloudrun/README.md](infra/cloudrun/README.md).

---

## Documentation Links
- [ARCHITECTURE.md](ARCHITECTURE.md): Full system architecture
- [python/README.md](python/README.md): Python engine usage
- [infra/aws/README.md](infra/aws/README.md): AWS deployment
- [infra/cloudrun/README.md](infra/cloudrun/README.md): GCP deployment

---

## Example Prompts
- "How do I run the backend tests?"
- "Where is the Python indexing logic?"
- "How do I deploy to AWS?"

---

## Next Steps
- For area-specific instructions, consider adding `applyTo`-based customizations for frontend, backend, or python.
- To extend agent behavior, see [agent-customization skill](https://github.com/features/copilot#customization) or create `/create-instruction`, `/create-agent`, or `/create-skill` files as needed.
