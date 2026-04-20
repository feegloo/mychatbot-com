from __future__ import annotations

import base64
import json
import logging
import os
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import docx2txt
import fitz  # pymupdf – C wrapper around MuPDF, already the fastest option
import pandas as pd
from openai import OpenAI
from pypdf import PdfReader

from .config import get_settings

logger = logging.getLogger(__name__)


TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml", ".yaml", ".yml", ".rtf"}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


# Strip storage uniqueness suffix from filenames for display.
# Mirrors frontend cleanFileName: UUID prefix and 16-char base62 suffix.
_UUID_PREFIX_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_", re.IGNORECASE
)
_SHORT_ID_SUFFIX_RE = re.compile(r"_[0-9A-Za-z]{16}(\.[^.]+)$")
_SHORT_ID_SUFFIX_NO_EXT_RE = re.compile(r"_[0-9A-Za-z]{16}$")


def clean_file_name(name: str) -> str:
    """Remove storage ID prefix/suffix from a filename for user-facing display."""
    name = _UUID_PREFIX_RE.sub("", name)
    result = _SHORT_ID_SUFFIX_RE.sub(r"\1", name)
    if result == name:
        result = _SHORT_ID_SUFFIX_NO_EXT_RE.sub("", name)
    return result


def _sanitize_text(text: str) -> str:
    """Remove problematic characters that cause issues in JSON/database.

    - Removes null characters (\x00)
    - Removes other control characters except newlines and tabs
    - Normalizes whitespace
    """
    # Remove null characters and other problematic control chars
    text = "".join(char for char in text if char == "\n" or char == "\t" or ord(char) >= 32)
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
    parts: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = _reflow_pdf_text(text.strip())
        parts.append(f"# Page {page_number}\n\n{text}")
    result = "\n\n".join(parts).strip()
    return _sanitize_text(result)


# ── Vision-based OCR ───────────────────────────────────────────────

# Minimum chars of real text (excluding headings like "# Page N") to consider
# text extraction successful. Below this threshold, OCR fallback is triggered.
_MIN_PAGE_TEXT_CHARS = 20


def _render_pdf_page_to_png(pdf_path: str, page_idx: int, *, dpi: int = 200) -> bytes:
    """Render a single PDF page to PNG bytes using PyMuPDF."""
    doc = fitz.open(pdf_path)
    page = doc[page_idx]
    zoom = dpi / 72  # 72 is the default PDF DPI
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    png_bytes = pix.tobytes("png")
    doc.close()
    return png_bytes


def ocr_pdf_page(pdf_path: str, page_idx: int) -> str:
    """Render a PDF page as image and extract text via GPT Vision OCR.

    Used as fallback when native text extraction yields no/minimal text
    (scanned PDFs, image-based PDFs, non-Latin scripts without text layer).
    """
    png_bytes = _render_pdf_page_to_png(pdf_path, page_idx)
    return _vision_extract_or_describe(
        png_bytes,
        mime_type="image/png",
        max_completion_tokens=5000,
        detail="high",
    )


def page_needs_ocr(page_text: str) -> bool:
    """Check whether a page's extracted text is too sparse and needs OCR.

    Strips the page heading (e.g. "# Page 5") before measuring.
    """
    stripped = re.sub(r"^#\s*Page\s+\d+\s*", "", page_text).strip()
    return len(stripped) < _MIN_PAGE_TEXT_CHARS


# ── PDF image extraction ───────────────────────────────────────────

MIN_IMAGE_SIZE = 5_000  # Skip tiny images (icons, bullets) under 5 KB
MIN_IMAGE_DIM = 50  # Skip images smaller than 50px in either dimension


# Thread count: use 2× CPU cores (hyper-threading) for IO-bound tasks
_NUM_THREADS = os.cpu_count() * 2 or 4


# OCR-first prompt is used for both page OCR fallback and extracted-image chunks so
# multilingual text-heavy scans (including RTL scripts) are indexed as literal text,
# while non-text visuals still produce concise semantic descriptions.
_VISION_OCR_FIRST_PROMPT = (
    "You are an OCR-first visual extraction engine for document indexing.\n"
    "Priority rules:\n"
    "1) If meaningful visible text exists, output an exact transcription in the original language/script.\n"
    "2) Never translate, normalize, paraphrase, summarize, or explain extracted text.\n"
    "3) Preserve paragraph/line structure and right-to-left order for Arabic/Hebrew/Persian/Urdu.\n"
    "4) If there is no meaningful text, output a concise factual description of the visual content.\n"
    "5) If both text and visual context matter, output the exact text first, then one short factual visual note."
)


def _vision_extract_or_describe(
    image_bytes: bytes,
    *,
    mime_type: str = "image/png",
    max_completion_tokens: int = 1200,
    detail: str = "auto",
) -> str:
    """Extract OCR text first, otherwise describe visual content."""
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model=settings.openai_chat_model,
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=settings.openai_reasoning_effort,
        messages=[
            {
                "role": "system",
                "content": _VISION_OCR_FIRST_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}", "detail": detail},
                    },
                ],
            },
        ],
    )
    return response.choices[0].message.content.strip()


def _describe_image(image_bytes: bytes, mime_type: str = "image/png") -> str:
    """Describe/extract text from an image using OCR-first vision."""
    return _vision_extract_or_describe(
        image_bytes,
        mime_type=mime_type,
        max_completion_tokens=1200,
        detail="auto",
    )


def _extract_and_save_images(pdf_path: Path, output_dir: Path) -> list[dict]:
    """Extract raw images from PDF and save as .png (CPU-bound, no API calls).

    Deduplicates by xref so each unique image is extracted only once
    (PDF templates/backgrounds reuse the same xref across many pages).

    Returns list of dicts with image metadata and saved png_bytes.
    """
    doc = fitz.open(str(pdf_path))
    saved: list[dict] = []
    seen_xrefs: set[int] = set()
    stem = pdf_path.stem

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        image_list = page.get_images(full=True)

        for img_idx, img_info in enumerate(image_list):
            xref = img_info[0]

            # Skip already-extracted images (same xref = same bytes)
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

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
            logger.info(
                f"🖼️  Extracted image: {image_name} ({width}x{height}, {len(image_bytes)} bytes)"
            )

            saved.append(
                {
                    "image_path": str(image_path),
                    "image_name": image_name,
                    "file_name": pdf_path.name,
                    "png_bytes": png_bytes,
                    "page": page_idx + 1,
                }
            )

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
    sections: list[str] = []
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
    if suffix in IMAGE_EXTENSIONS:
        return extract_image(path)
    if suffix in TEXT_EXTENSIONS:
        return extract_plain_text(path)

    # fallback for text-like files
    return extract_plain_text(path)


_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


def extract_image(path: Path) -> str:
    """Describe a standalone image file using vision model."""
    image_bytes = path.read_bytes()
    mime = _MIME_TYPES.get(path.suffix.lower(), "image/png")
    try:
        description = _describe_image(image_bytes, mime_type=mime)
        logger.info(f"\U0001f5bc\ufe0f  Described image {path.name}: {description[:80]}...")
        return _sanitize_text(description)
    except Exception as e:
        logger.warning(f"\u26a0\ufe0f  Vision description failed for {path.name}: {e}")
        return f"Image file: {path.name}"


def extract_many(paths: Iterable[str]) -> list[dict]:
    documents = []
    all_images = []
    for file_path in paths:
        p = Path(file_path)
        suffix = p.suffix.lower()

        # Standalone image files: describe with vision and add as image entry
        if suffix in IMAGE_EXTENSIONS:
            text = extract_text(file_path)
            documents.append(
                {
                    "file_path": file_path,
                    "file_name": p.name,
                    "text": text,
                }
            )
            # Also register as an image so the thumbnail shows in citations
            output_dir = p.parent
            image_name = p.name
            all_images.append(
                {
                    "image_path": str(p),
                    "image_name": image_name,
                    "file_name": p.name,
                    "description": text,
                    "page": None,
                }
            )
            logger.info(f"\U0001f5bc\ufe0f  Processed standalone image: {p.name}")
            continue

        text = extract_text(file_path)
        documents.append(
            {
                "file_path": file_path,
                "file_name": p.name,
                "text": text,
            }
        )
        # Extract images from PDFs
        if suffix == ".pdf":
            output_dir = p.parent
            try:
                images = extract_pdf_images(p, output_dir)
                all_images.extend(images)
                logger.info(f"\U0001f5bc\ufe0f  Found {len(images)} images in {p.name}")
            except Exception as e:
                logger.warning(f"⚠️  Image extraction failed for {file_path}: {e}")
    return documents, all_images
