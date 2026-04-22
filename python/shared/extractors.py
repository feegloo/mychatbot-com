from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import docx2txt
import fitz  # pymupdf – C wrapper around MuPDF, already the fastest option
import pandas as pd
from openai import OpenAI

from .llm_instrument import traced_openai_call
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
# Skip decorative images with extreme aspect ratios (lines, borders, separators).
# A ratio > 10:1 reliably catches thin horizontal/vertical rules while keeping
# narrow-but-meaningful images (e.g. a tall infographic with 8:1 proportions).
MAX_IMAGE_ASPECT_RATIO = 10


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

    messages = [
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
    ]
    text, _usage = traced_openai_call(
        client=client,
        messages=messages,
        model=settings.openai_chat_model,
        operation="vision_ocr",
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=settings.openai_reasoning_effort,
    )
    return text.strip()


def _describe_image(image_bytes: bytes, mime_type: str = "image/png") -> str:
    """Describe/extract text from an image using OCR-first vision."""
    return _vision_extract_or_describe(
        image_bytes,
        mime_type=mime_type,
        max_completion_tokens=1200,
        detail="auto",
    )


# Maximum chars of page text passed as context to the vision model.
# Keeps the prompt focused without exceeding token limits.
_IMAGE_CONTEXT_PAGE_TEXT_MAX = 800


def _describe_image_with_context(
    image_bytes: bytes,
    *,
    document_context: str = "",
    page_text: str = "",
    mime_type: str = "image/png",
) -> str:
    """Describe an image with document and page context for richer RAG embeddings.

    Passes the document title/topic and surrounding page text so the vision
    model can produce descriptions that use domain vocabulary (e.g. part names,
    procedure steps) matching what users will actually search for.

    Falls back to plain `_describe_image` when no context is available.
    """
    if not document_context and not page_text:
        return _describe_image(image_bytes, mime_type=mime_type)

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    # Trim page text to avoid prompt bloat
    page_excerpt = page_text[:_IMAGE_CONTEXT_PAGE_TEXT_MAX].strip() if page_text else ""

    context_lines: list[str] = []
    if document_context:
        context_lines.append(f"Document: {document_context}")
    if page_excerpt:
        context_lines.append(f"Surrounding page text:\n{page_excerpt}")

    context_block = "\n".join(context_lines)

    system_prompt = (
        "You are a document image analyst creating searchable descriptions for RAG indexing.\n"
        "Your descriptions must be specific and use the vocabulary of the document's domain "
        "so they match the words users will type when searching.\n\n"
        "Rules:\n"
        "1. If meaningful text is visible (labels, captions, step numbers, part names), "
        "transcribe it exactly first.\n"
        "2. Identify the image type: diagram, photo, exploded view, warning symbol, "
        "chart, illustration, procedure step, etc.\n"
        "3. Describe the content concretely using domain terminology from the document context.\n"
        "4. For assembly/maintenance diagrams: name the part or action being shown.\n"
        "5. For instructional images: describe what step or procedure is illustrated.\n"
        "6. Do NOT start with 'This image shows' or 'This is a picture of'.\n"
        "7. Output 2–5 focused sentences."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"{context_block}\n\n"
                        "Describe the image below using domain-specific vocabulary "
                        "from the document context above."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64}", "detail": "auto"},
                },
            ],
        },
    ]

    text, _usage = traced_openai_call(
        client=client,
        messages=messages,
        model=settings.openai_chat_model,
        operation="vision_describe_with_context",
        max_completion_tokens=1200,
        reasoning_effort=settings.openai_reasoning_effort,
    )
    return text.strip()


def claim_xref_if_drawn_on_page(
    page: "fitz.Page",
    xref: int,
    seen_xrefs: set[int],
    seen_xrefs_lock: threading.Lock,
) -> bool:
    """Atomically claim ``xref`` on ``page`` if the image is rendered there.

    ``page.get_images(full=True)`` returns every image in the page's resource
    dict, which in many PDFs is inherited from the Pages tree root — so the
    same xref is reported on every page regardless of where it is drawn.
    Using ``page.get_image_rects(xref)`` confirms the image is visually
    present on this page, so we attribute the image to the page it is
    actually rendered on instead of the first page that merely lists it.

    Returns True when the caller should extract the image on this page.
    Returns False when either:
      - the xref is already claimed by another page (cross-page dedup), or
      - the image is only referenced via the page's (inherited) resource
        dict and has no draw rectangles on this page.

    ``get_image_rects`` is treated as best-effort: unexpected exceptions
    preserve pre-fix behaviour (the image is claimed on this page) rather
    than silently dropping the image entirely.
    """
    # Lockless fast path: skip xrefs already claimed by another page.
    if xref in seen_xrefs:
        return False
    try:
        rects = page.get_image_rects(xref)
    except Exception:
        rects = None
    if rects is not None and len(rects) == 0:
        return False
    with seen_xrefs_lock:
        if xref in seen_xrefs:
            return False
        seen_xrefs.add(xref)
    return True


def _extract_and_save_images(pdf_path: Path, output_dir: Path) -> list[dict]:
    """Extract raw images from PDF and save as .png (CPU-bound, no API calls).

    Deduplicates by xref so each unique image is extracted only once
    (PDF templates/backgrounds reuse the same xref across many pages).

    Returns list of dicts with image metadata and saved png_bytes.
    """
    doc = fitz.open(str(pdf_path))
    saved: list[dict] = []
    seen_xrefs: set[int] = set()
    # Single-threaded path, but use a lock so the dedup helper is shared with
    # the parallel worker path without code duplication.
    seen_xrefs_lock = threading.Lock()
    stem = pdf_path.stem

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        image_list = page.get_images(full=True)

        for img_idx, img_info in enumerate(image_list):
            xref = img_info[0]

            if not claim_xref_if_drawn_on_page(page, xref, seen_xrefs, seen_xrefs_lock):
                continue

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
            if min(width, height) > 0 and max(width, height) / min(width, height) > MAX_IMAGE_ASPECT_RATIO:
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
