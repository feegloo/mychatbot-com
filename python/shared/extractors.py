from __future__ import annotations

import base64
import csv
import json
import logging
import re
from pathlib import Path
from typing import Iterable, List

import docx2txt
import fitz  # pymupdf
import pandas as pd
from openai import OpenAI
from pypdf import PdfReader

from .config import get_settings

logger = logging.getLogger(__name__)


TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml", ".yaml", ".yml", ".rtf"
}


def _sanitize_text(text: str) -> str:
    """Remove problematic characters that cause issues in JSON/database.
    
    - Removes null characters (\x00)
    - Removes other control characters except newlines and tabs
    - Normalizes whitespace
    """
    # Remove null characters and other problematic control chars
    text = ''.join(char for char in text if char == '\n' or char == '\t' or ord(char) >= 32)
    return text


def _reflow_pdf_text(raw: str) -> str:
    """Join lines broken by PDF layout into flowing paragraphs.

    Only blank lines (double newlines) are treated as paragraph breaks.
    All other single newlines are treated as soft wraps from the PDF layout
    and joined with a space.
    """
    paragraphs = raw.split("\n\n")
    reflowed: list[str] = []
    for para in paragraphs:
        # Join all lines within a paragraph into one continuous string
        joined = " ".join(line.strip() for line in para.split("\n") if line.strip())
        if joined:
            reflowed.append(joined)
    return "\n\n".join(reflowed)


def extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: List[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = _reflow_pdf_text(text.strip())
        parts.append(f"# Page {page_number}\n\n{text}")
    result = "\n\n".join(parts).strip()
    return _sanitize_text(result)


# ── PDF image extraction ───────────────────────────────────────────

MIN_IMAGE_SIZE = 5_000  # Skip tiny images (icons, bullets) under 5 KB
MIN_IMAGE_DIM = 50      # Skip images smaller than 50px in either dimension


def _describe_image(image_bytes: bytes) -> str:
    """Use GPT-4 vision to describe an image."""
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model=settings.openai_chat_model,
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image concisely. Include all visible text, data, labels, and key visual elements. This description will be used for search retrieval."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "low"}},
            ],
        }],
    )
    return response.choices[0].message.content.strip()


def extract_pdf_images(pdf_path: Path, output_dir: Path) -> list[dict]:
    """Extract images from a PDF, save as .png, describe with vision model.

    Returns list of dicts: {image_path, file_name, description, page}
    """
    doc = fitz.open(str(pdf_path))
    images: list[dict] = []
    stem = pdf_path.stem

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        image_list = page.get_images(full=True)

        for img_idx, img_info in enumerate(image_list):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
            except Exception:
                continue

            image_bytes = base_image["image"]
            width = base_image.get("width", 0)
            height = base_image.get("height", 0)

            # Skip tiny/decorative images
            if len(image_bytes) < MIN_IMAGE_SIZE:
                continue
            if width < MIN_IMAGE_DIM or height < MIN_IMAGE_DIM:
                continue

            # Save image (extract_image returns native format bytes)
            img_ext = base_image.get("ext", "png")
            image_name = f"{stem}_page{page_idx + 1}_img{img_idx + 1}.png"
            image_path = output_dir / image_name

            if img_ext == "png":
                image_path.write_bytes(image_bytes)
            else:
                # Convert non-PNG formats to PNG via Pixmap
                pix = fitz.Pixmap(image_bytes)
                if pix.n > 4:  # CMYK → RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                pix.save(str(image_path))

            png_bytes = image_path.read_bytes()

            logger.info(f"🖼️  Extracted image: {image_name} ({width}x{height}, {len(image_bytes)} bytes)")

            try:
                description = _describe_image(png_bytes)
            except Exception as e:
                logger.warning(f"⚠️  Failed to describe {image_name}: {e}")
                description = f"Image from page {page_idx + 1} of {pdf_path.name}"

            images.append({
                "image_path": str(image_path),
                "image_name": image_name,
                "file_name": pdf_path.name,
                "description": description,
                "page": page_idx + 1,
            })

    doc.close()
    return images


def extract_docx(path: Path) -> str:
    result = docx2txt.process(str(path)).strip()
    return _sanitize_text(result)


def extract_spreadsheet(path: Path) -> str:
    excel_file = pd.ExcelFile(path)
    sections: List[str] = []
    for sheet_name in excel_file.sheet_names:
        df = excel_file.parse(sheet_name)
        sections.append(f"# Sheet: {sheet_name}\n\n{df.fillna('').to_csv(index=False)}")
    result = "\n\n".join(sections).strip()
    return _sanitize_text(result)


def extract_csv(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        result = handle.read().strip()
    return _sanitize_text(result)


def extract_json(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        payload = json.load(handle)
    result = json.dumps(payload, ensure_ascii=False, indent=2)
    return _sanitize_text(result)


def extract_plain_text(path: Path) -> str:
    result = path.read_text(encoding="utf-8", errors="ignore").strip()
    return _sanitize_text(result)


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
    all_images = []
    for file_path in paths:
        text = extract_text(file_path)
        documents.append({
            "file_path": file_path,
            "file_name": Path(file_path).name,
            "text": text,
        })
        # Extract images from PDFs
        if Path(file_path).suffix.lower() == ".pdf":
            output_dir = Path(file_path).parent
            try:
                images = extract_pdf_images(Path(file_path), output_dir)
                all_images.extend(images)
                logger.info(f"🖼️  Found {len(images)} images in {Path(file_path).name}")
            except Exception as e:
                logger.warning(f"⚠️  Image extraction failed for {file_path}: {e}")
    return documents, all_images
