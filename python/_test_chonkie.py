"""Quick test to explore Chonkie behavior."""
from chonkie import RecursiveChunker, RecursiveRules

c = RecursiveChunker(
    chunk_size=1600,
    tokenizer="character",
    rules=RecursiveRules.from_recipe("markdown"),
    min_characters_per_chunk=24,
)

text = """# Project Overview

This is the first section of the document. It contains important information about the project goals and objectives. The team has been working diligently on delivering a high-quality solution that meets all requirements.

## Architecture

The system uses a microservices architecture with the following components:

1. Frontend - Built with Vue 3 and TypeScript
2. Backend - Node.js with Koa framework
3. AI Engine - Python with LangChain
4. Vector Database - Chroma for embeddings
5. Metadata Database - PostgreSQL

Each component is designed to be independently deployable and scalable.

## Deployment

The application can be deployed to AWS or GCP using the provided infrastructure scripts.

### AWS Deployment

Use the CloudFormation templates in the infra/aws directory.

### GCP Deployment

Use the Cloud Run configuration in infra/cloudrun directory.

## Getting Started

Follow these steps to get the application running locally:

1. Clone the repository
2. Install dependencies for each component
3. Start the Docker containers
4. Run the development servers"""

chunks = c(text)
print(f"{len(chunks)} chunks")
for i, ch in enumerate(chunks):
    print(f"  [{i}] chars={ch.token_count}")
    print(f"       text={repr(ch.text[:120])}...")
    print(f"       id={ch.id}, start={ch.start_index}, end={ch.end_index}")
    print()

# Also test plain text (no markdown headers)
print("=== PLAIN TEXT TEST ===")
plain = """Aurora - Instrukcje Obslugi
Wersja 1.0

1. Przeglad systemu
Aurora to zaawansowany system do zarzadzania dokumentami. System sklada sie z wielu komponentow.

2. Instalacja
Aby zainstalowac system Aurora, wykonaj nastepujace kroki:
- Pobierz instalator ze strony
- Uruchom plik setup.exe
- Postepuj zgodnie z instrukcjami

3. Konfiguracja
Po instalacji nalezy skonfigurowac system. Otworz panel administratora.

4. Uzytkowanie
System Aurora umozliwia tworzenie, edycje i zarzadzanie dokumentami."""

chunks2 = c(plain)
print(f"{len(chunks2)} chunks")
for i, ch in enumerate(chunks2):
    print(f"  [{i}] chars={ch.token_count}")
    print(f"       text={repr(ch.text[:120])}...")
    print()

# Test with LARGE text to see splitting
print("=== LARGE TEXT TEST ===")
large = "\n\n".join([f"## Section {i}\n\nThis is paragraph {i} with some content. " * 20 for i in range(20)])
chunks3 = c(large)
print(f"Total chars: {len(large)}, {len(chunks3)} chunks")
for i, ch in enumerate(chunks3):
    print(f"  [{i}] chars={ch.token_count} text={repr(ch.text[:80])}...")

