"""Multi-format file description for the Ralph loop.

Goal: turn each input file in a task folder into a few hundred tokens of
plain-English description that an LLM coding agent can read.

Kept minimal on purpose — only depends on `pypdf`, `Pillow`, `openai`. If the
chatrag-app python engine is importable we delegate to its richer extractors
(``python.src.shared.extractors``) for PDF text + image vision, otherwise we
fall back to local implementations.

Design notes:
- Pure functions wherever possible. State (the OpenAI client) is built once at
  module import time so callers don't pass it around.
- We never raise on a single unreadable file; describing is best-effort and
  bubbles a one-line ``[ralph: could not describe X: <reason>]`` instead.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger(__name__)

TEXT_EXTS = {".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".yaml",
             ".yml", ".toml", ".ini", ".cfg", ".html", ".htm", ".xml", ".log"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"}
PDF_EXTS = {".pdf"}
DOCX_EXTS = {".docx"}
XLSX_EXTS = {".xlsx", ".xls"}

# Keep file-description prompts well below model context. Image describe uses
# vision and is naturally short; text/PDF we truncate to a generous ceiling.
_MAX_TEXT_CHARS = 16_000
_MAX_DESCRIBE_CHARS = 4_000

DESCRIBE_MODEL = os.getenv("RALPH_DESCRIBE_MODEL", "gpt-4o-mini")


def _openai_client():
    # Imported lazily so `import file_describer` works without OPENAI_API_KEY
    # set (e.g. when only describing plain-text files).
    from openai import OpenAI  # noqa: WPS433

    return OpenAI()


def _read_text_file(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"[ralph: could not read {path.name}: {exc}]"
    return raw[:_MAX_TEXT_CHARS]


def _read_pdf(path: Path) -> str:
    """Prefer chatrag's extractor (handles OCR); fall back to pypdf."""
    try:
        from python.src.shared.extractors import extract_pdf  # type: ignore

        return extract_pdf(path)[:_MAX_TEXT_CHARS]
    except Exception:  # noqa: BLE001 — fall through to local extractor
        pass
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        chunks = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(chunks)[:_MAX_TEXT_CHARS]
    except Exception as exc:  # noqa: BLE001
        return f"[ralph: could not parse PDF {path.name}: {exc}]"


def _describe_image(path: Path) -> str:
    try:
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        client = _openai_client()
        resp = client.chat.completions.create(
            model=DESCRIBE_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Describe this image precisely as design / spec input "
                                "for a coding agent. Note layout, UI components, copy, "
                                "states, any visible API or code. Be concrete."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{data}"},
                        },
                    ],
                }
            ],
            max_tokens=600,
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001
        return f"[ralph: could not describe image {path.name}: {exc}]"


def _read_docx(path: Path) -> str:
    try:
        import docx2txt  # type: ignore

        return (docx2txt.process(str(path)) or "")[:_MAX_TEXT_CHARS]
    except Exception as exc:  # noqa: BLE001
        return f"[ralph: could not parse docx {path.name}: {exc}]"


def _read_spreadsheet(path: Path) -> str:
    try:
        import pandas as pd  # type: ignore

        df = pd.read_excel(path) if path.suffix.lower() == ".xlsx" else pd.read_csv(path)
        return df.to_csv(index=False)[:_MAX_TEXT_CHARS]
    except Exception as exc:  # noqa: BLE001
        return f"[ralph: could not parse spreadsheet {path.name}: {exc}]"


def _summarize_long_text(text: str, source_name: str) -> str:
    """Compress a long file's body into a few hundred tokens of useful summary."""
    if len(text) <= _MAX_DESCRIBE_CHARS:
        return text
    try:
        client = _openai_client()
        resp = client.chat.completions.create(
            model=DESCRIBE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You compress documents for a coding agent. Preserve every "
                        "fact relevant to building software: requirements, acceptance "
                        "criteria, API shapes, code, UI copy, edge cases. Drop fluff."
                    ),
                },
                {
                    "role": "user",
                    "content": f"# {source_name}\n\n{text[:_MAX_TEXT_CHARS]}",
                },
            ],
            max_tokens=900,
        )
        return resp.choices[0].message.content or text[:_MAX_DESCRIBE_CHARS]
    except Exception as exc:  # noqa: BLE001
        logger.warning("describe summarize failed for %s: %s", source_name, exc)
        return text[:_MAX_DESCRIBE_CHARS]


def describe_file(path: Path) -> str:
    """Return a plain-text description of a single file. Never raises."""
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTS:
        return _describe_image(path)
    if suffix in PDF_EXTS:
        return _summarize_long_text(_read_pdf(path), path.name)
    if suffix in DOCX_EXTS:
        return _summarize_long_text(_read_docx(path), path.name)
    if suffix in XLSX_EXTS or suffix == ".csv":
        return _summarize_long_text(_read_spreadsheet(path), path.name)
    if suffix in TEXT_EXTS or suffix == "":
        return _summarize_long_text(_read_text_file(path), path.name)
    # Unknown binary — skip with a marker rather than guessing.
    return f"[ralph: skipped unknown file type {path.name} ({suffix or 'no-ext'})]"


def describe_files(paths: Iterable[Path]) -> dict[str, str]:
    """Batch describe; returns {relative_path_string: description}."""
    out: dict[str, str] = {}
    for p in paths:
        logger.info("describing %s", p)
        out[str(p)] = describe_file(p)
    return out
