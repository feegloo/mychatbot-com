from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, List

import docx2txt
import pandas as pd
from pypdf import PdfReader


TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml", ".yaml", ".yml", ".rtf"
}


def extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: List[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        parts.append(f"# Page {page_number}\n\n{text.strip()}")
    return "\n\n".join(parts).strip()


def extract_docx(path: Path) -> str:
    return docx2txt.process(str(path)).strip()


def extract_spreadsheet(path: Path) -> str:
    excel_file = pd.ExcelFile(path)
    sections: List[str] = []
    for sheet_name in excel_file.sheet_names:
        df = excel_file.parse(sheet_name)
        sections.append(f"# Sheet: {sheet_name}\n\n{df.fillna('').to_csv(index=False)}")
    return "\n\n".join(sections).strip()


def extract_csv(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return handle.read().strip()


def extract_json(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        payload = json.load(handle)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def extract_plain_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def extract_text(path_str: str) -> str:
    path = Path(path_str)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".docx":
        return extract_docx(path)
    if suffix in {".xls", ".xlsx"}:
        return extract_spreadsheet(path)
    if suffix == ".csv":
        return extract_csv(path)
    if suffix == ".json":
        return extract_json(path)
    if suffix in TEXT_EXTENSIONS:
        return extract_plain_text(path)

    # fallback for text-like files
    return extract_plain_text(path)


def extract_many(paths: Iterable[str]) -> list[dict]:
    documents = []
    for file_path in paths:
        text = extract_text(file_path)
        documents.append({
            "file_path": file_path,
            "file_name": Path(file_path).name,
            "text": text,
        })
    return documents
