from __future__ import annotations

import base64
import csv
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, List

import docx2txt
import fitz  # pymupdf – C wrapper around MuPDF, already the fastest option
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


# Thread count: use 2× CPU cores (hyper-threading) for IO-bound tasks
_NUM_THREADS = os.cpu_count() * 2 or 4


def _describe_image(image_bytes: bytes) -> str:
    """Use GPT-4 vision to describe an image."""
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model=settings.openai_chat_model,
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Return a brief factual caption (2-3 sentences max). State: subject/type, key text/labels/data visible, and visual layout. No filler words."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "low"}},
            ],
        }],
    )
    return response.choices[0].message.content.strip()


def _extract_and_save_images(pdf_path: Path, output_dir: Path) -> list[dict]:
    """Extract raw images from PDF and save as .png (CPU-bound, no API calls).

    Returns list of dicts with image metadata and saved png_bytes.
    """
    doc = fitz.open(str(pdf_path))
    saved: list[dict] = []
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

            saved.append({
                "image_path": str(image_path),
                "image_name": image_name,
                "file_name": pdf_path.name,
                "png_bytes": png_bytes,
                "page": page_idx + 1,
            })

    doc.close()
    return saved


def _describe_one(item: dict) -> dict:
    """Describe a single extracted image. Used as ThreadPoolExecutor target."""
    try:
        description = _describe_image(item["png_bytes"])
    except Exception as e:
        logger.warning(f"⚠️  Failed to describe {item['image_name']}: {e}")
        description = f"Image from page {item['page']} of {item['file_name']}"
    return {
        "image_path": item["image_path"],
        "image_name": item["image_name"],
        "file_name": item["file_name"],
        "description": description,
        "page": item["page"],
    }


def extract_pdf_images(pdf_path: Path, output_dir: Path) -> list[dict]:
    """Extract images from a PDF, save as .png, describe with vision model.

    Phase 1: Extract & save images (CPU-bound, runs in-process via fast C lib).
    Phase 2: Describe all images in parallel (IO-bound API calls, uses all threads).

    Returns list of dicts: {image_path, file_name, description, page}
    """
    # Phase 1 – fast C-level extraction (PyMuPDF/MuPDF)
    saved = _extract_and_save_images(pdf_path, output_dir)
    if not saved:
        return []

    # Phase 2 – parallel API descriptions (IO-bound → threads)
    logger.info(f"🖼️  Describing {len(saved)} images in parallel ({_NUM_THREADS} threads)")
    images: list[dict] = []
    with ThreadPoolExecutor(max_workers=_NUM_THREADS) as pool:
        futures = {pool.submit(_describe_one, item): item for item in saved}
        for future in as_completed(futures):
            images.append(future.result())

    # Preserve original page order
    images.sort(key=lambda x: (x["page"], x["image_path"]))
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
