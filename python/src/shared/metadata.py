"""Extract file metadata (EXIF, PDF info, basic file stats) + reverse image search."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}
PDF_EXTENSIONS = {".pdf"}


def _safe_exif_value(value: Any) -> Any:
    """Convert EXIF value to JSON-serializable type."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)
    if isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, tuple):
        return [_safe_exif_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_exif_value(v) for k, v in value.items()}
    return str(value)


def _parse_gps_coord(coord: tuple, ref: str) -> float | None:
    """Convert GPS DMS tuple + ref to decimal degrees."""
    try:
        degrees = float(coord[0])
        minutes = float(coord[1])
        seconds = float(coord[2])
        decimal = degrees + minutes / 60 + seconds / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except Exception:
        return None


def reverse_geocode_coordinates(lat: float, lon: float) -> str | None:
    """Resolve GPS coordinates to a rich human-readable location description via OpenAI web search.

    Uses the OpenAI Responses API with the web_search_preview tool to look up the
    location. Returns 2-4 sentences covering country, division/region, district,
    sub-district, and any notable geographic features (rivers, coast, agricultural
    character). Concise but specific — enough context to be meaningful to the user.
    Returns None when the lookup fails or the API is unavailable.
    """
    try:
        from openai import OpenAI

        from .config import get_settings

        settings = get_settings()
        if not settings.openai_api_key:
            return None

        client = OpenAI(api_key=settings.openai_api_key, timeout=15.0)
        query = (
            f"Locate GPS coordinates {lat:.6f}, {lon:.6f} precisely. "
            f"Provide a concise 2-3 sentence description covering: "
            f"(1) the country and administrative division/region, "
            f"(2) the district and sub-district (upazila / county / commune / municipality), "
            f"(3) the nearest named village, town, or landmark if identifiable, "
            f"(4) any notable geographic character "
            f"(coastal, riverine, agricultural, urban, mountainous, etc.). "
            f"Be specific and factual. No preamble, no bullet points, plain prose only."
        )
        response = client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search_preview"}],
            input=query,
        )
        place = (response.output_text or "").strip()
        if place:
            logger.info(f"📍 Reverse geocoded ({lat}, {lon}) → {place[:120]}...")
            return place
        return None
    except Exception as e:
        logger.warning(f"⚠️  Reverse geocoding failed for ({lat}, {lon}): {e}")
        return None


def extract_image_metadata(file_path: str, web_search: bool = False) -> dict:
    """Extract EXIF and basic metadata from an image file.

    Args:
        file_path: Path to the image file.
        web_search: If True, also run Google Vision reverse image search.
                    Should only be enabled for standalone uploaded images.
    """
    from PIL import Image
    from PIL.ExifTags import GPSTAGS, TAGS

    p = Path(file_path)
    metadata: dict[str, Any] = {
        "file_type": "image",
        "file_name": p.name,
        "file_size_bytes": p.stat().st_size,
        "file_created": datetime.fromtimestamp(p.stat().st_ctime).isoformat(),
        "file_modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }

    try:
        img = Image.open(file_path)
        metadata["image_width"] = img.size[0]
        metadata["image_height"] = img.size[1]
        metadata["image_format"] = img.format
        metadata["image_mode"] = img.mode

        exif_data = img._getexif()
        if exif_data:
            exif_info: dict[str, Any] = {}
            gps_info: dict[str, Any] = {}

            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, str(tag_id))

                if tag_name == "GPSInfo":
                    for gps_tag_id, gps_value in value.items():
                        gps_tag_name = GPSTAGS.get(gps_tag_id, str(gps_tag_id))
                        gps_info[gps_tag_name] = _safe_exif_value(gps_value)
                elif tag_name == "MakerNote":
                    continue  # Skip raw binary maker notes
                else:
                    exif_info[tag_name] = _safe_exif_value(value)

            # Extract key fields
            if "Make" in exif_info:
                metadata["camera_make"] = exif_info["Make"]
            if "Model" in exif_info:
                metadata["camera_model"] = exif_info["Model"]
            if "DateTime" in exif_info:
                metadata["date_taken"] = exif_info["DateTime"]
            if "DateTimeOriginal" in exif_info:
                metadata["date_taken"] = exif_info["DateTimeOriginal"]
            if "ExposureTime" in exif_info:
                metadata["exposure_time"] = exif_info["ExposureTime"]
            if "FNumber" in exif_info:
                metadata["f_number"] = exif_info["FNumber"]
            if "ISOSpeedRatings" in exif_info:
                metadata["iso"] = exif_info["ISOSpeedRatings"]
            if "FocalLength" in exif_info:
                metadata["focal_length"] = exif_info["FocalLength"]
            if "LensModel" in exif_info:
                metadata["lens_model"] = exif_info["LensModel"]
            if "Software" in exif_info:
                metadata["software"] = exif_info["Software"]
            if "Copyright" in exif_info:
                metadata["copyright"] = exif_info["Copyright"]
            if "Artist" in exif_info:
                metadata["artist"] = exif_info["Artist"]
            if "ImageDescription" in exif_info:
                metadata["description"] = exif_info["ImageDescription"]

            # GPS location
            if gps_info:
                lat = None
                lon = None
                if "GPSLatitude" in gps_info and "GPSLatitudeRef" in gps_info:
                    lat = _parse_gps_coord(gps_info["GPSLatitude"], gps_info["GPSLatitudeRef"])
                if "GPSLongitude" in gps_info and "GPSLongitudeRef" in gps_info:
                    lon = _parse_gps_coord(gps_info["GPSLongitude"], gps_info["GPSLongitudeRef"])
                if lat is not None and lon is not None:
                    metadata["gps_latitude"] = lat
                    metadata["gps_longitude"] = lon
                    place_name = reverse_geocode_coordinates(lat, lon)
                    if place_name:
                        metadata["gps_place_name"] = place_name
                if "GPSAltitude" in gps_info:
                    metadata["gps_altitude"] = _safe_exif_value(gps_info["GPSAltitude"])

            metadata["exif"] = exif_info

    except Exception as e:
        logger.warning(f"Failed to extract image metadata for {file_path}: {e}")

    # Reverse image search via Google Vision API (only for standalone uploaded images)
    if not web_search:
        return metadata

    try:
        from .image_search import identify_from_web_results, reverse_image_search

        web_results = reverse_image_search(file_path)
        if web_results:
            metadata["web_detection"] = web_results

            # Try to identify person/subject from web results
            image_desc = metadata.get("description", "")
            identification = identify_from_web_results(web_results, image_desc)
            if identification and identification.get("identified_name"):
                metadata["identified_name"] = identification["identified_name"]
                metadata["identification"] = identification
    except Exception as e:
        logger.warning(f"⚠️  Reverse image search failed for {file_path}: {e}")

    return metadata


def _extract_pdf_hyperlinks(file_path: str) -> dict[str, str]:
    """Extract clickable hyperlink annotations from a PDF using PyMuPDF.

    Returns a dict of {display_text: url} for every URI link annotation found.
    When the link rectangle contains no extractable text, the URL itself is used
    as the key so the LLM still sees the URL.
    """
    import fitz  # pymupdf

    links: dict[str, str] = {}
    try:
        doc = fitz.open(file_path)
        for page in doc:
            for link in page.get_links():
                # kind 2 == LINK_URI in PyMuPDF
                if link.get("kind") != 2:
                    continue
                uri = link.get("uri", "").strip()
                if not uri or not uri.startswith(("http://", "https://")):
                    continue
                # Try to find the display text inside the link rectangle
                rect = link.get("from")
                display = ""
                if rect:
                    words = page.get_text("words", clip=rect)
                    display = " ".join(w[4] for w in words).strip()
                key = display if display else uri
                # Keep the first URL for a given display text (avoid duplicates)
                links.setdefault(key, uri)
        doc.close()
    except Exception as e:
        logger.warning(f"⚠️  Could not extract PDF hyperlinks from {file_path}: {e}")
    return links


def extract_pdf_metadata(file_path: str) -> dict:
    """Extract metadata from a PDF file."""
    from pypdf import PdfReader

    p = Path(file_path)
    metadata: dict[str, Any] = {
        "file_type": "pdf",
        "file_name": p.name,
        "file_size_bytes": p.stat().st_size,
        "file_created": datetime.fromtimestamp(p.stat().st_ctime).isoformat(),
        "file_modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }

    try:
        reader = PdfReader(file_path)
        metadata["page_count"] = len(reader.pages)

        info = reader.metadata
        if info:
            if info.title:
                metadata["title"] = str(info.title)
            if info.author:
                metadata["author"] = str(info.author)
            if info.subject:
                metadata["subject"] = str(info.subject)
            if info.creator:
                metadata["creator"] = str(info.creator)
            if info.producer:
                metadata["producer"] = str(info.producer)
            if info.creation_date:
                metadata["creation_date"] = info.creation_date.isoformat()
            if info.modification_date:
                metadata["modification_date"] = info.modification_date.isoformat()
    except Exception as e:
        logger.warning(f"Failed to extract PDF metadata for {file_path}: {e}")

    hyperlinks = _extract_pdf_hyperlinks(file_path)
    if hyperlinks:
        metadata["pdf_hyperlinks"] = hyperlinks

    return metadata


def extract_file_metadata(file_path: str) -> dict:
    """Extract basic metadata for any file type."""
    p = Path(file_path)
    metadata: dict[str, Any] = {
        "file_type": "document",
        "file_name": p.name,
        "file_size_bytes": p.stat().st_size,
        "file_created": datetime.fromtimestamp(p.stat().st_ctime).isoformat(),
        "file_modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }
    return metadata


def extract_metadata(file_path: str, web_search: bool = False) -> dict:
    """Extract metadata based on file type. Returns a JSON-serializable dict."""
    p = Path(file_path)
    suffix = p.suffix.lower()

    if suffix in IMAGE_EXTENSIONS:
        return extract_image_metadata(file_path, web_search=web_search)
    elif suffix in PDF_EXTENSIONS:
        return extract_pdf_metadata(file_path)
    else:
        return extract_file_metadata(file_path)


def extract_metadata_many(file_paths: list[str]) -> dict[str, dict]:
    """Extract metadata for multiple files. Returns {filename: metadata_dict}.

    Only extracts local metadata (EXIF, PDF info, file stats).
    Does NOT call external APIs — use enrich_metadata_web() separately for that.
    """
    result = {}
    for fp in file_paths:
        try:
            p = Path(fp)
            meta = extract_metadata(fp, web_search=False)
            result[p.name] = meta
            logger.info(f"📋 Extracted metadata for {p.name}: {list(meta.keys())}")
        except Exception as e:
            logger.warning(f"⚠️ Metadata extraction failed for {fp}: {e}")
            result[Path(fp).name] = {"file_name": Path(fp).name, "error": str(e)}
    return result


def enrich_metadata_web(
    file_paths: list[str],
    exif_metadata: dict[str, dict] | None = None,
    welcome_message: str = "",
) -> dict[str, dict]:
    """Run Google Vision reverse image search + LLM identification for image files.

    Combines three sources for the final "recognize person name" LLM call:
      1. EXIF metadata (already extracted, passed in)
      2. AI description / welcome message (already generated, passed in)
      3. Google Vision web detection (fetched here)

    Returns {filename: enrichment_dict} with keys like
    web_detection, identified_name, identification.
    Returns empty dict if no images.
    """
    from .image_search import identify_from_web_results, reverse_image_search

    image_paths = [fp for fp in file_paths if Path(fp).suffix.lower() in IMAGE_EXTENSIONS]
    logger.info(
        f"🔍 enrich_metadata_web: {len(file_paths)} file_paths, "
        f"{len(image_paths)} images, "
        f"exif keys={list((exif_metadata or {}).keys())}, "
        f"welcome_message={len(welcome_message)} chars"
    )
    if not image_paths:
        logger.info("🔍 No image paths found after filtering, returning empty")
        return {}

    exif_metadata = exif_metadata or {}

    result = {}
    for fp in image_paths:
        p = Path(fp)
        logger.info(f"🔍 Processing image: {p.name} (exists={p.exists()})")
        enrichment: dict[str, Any] = {}

        # Step 3: fetch Vision API web detection
        web_results = None
        try:
            web_results = reverse_image_search(fp)
            if web_results:
                enrichment["web_detection"] = web_results
                logger.info(f"🔍 Vision API returned web_detection for {p.name}")
            else:
                logger.info(f"🔍 Vision API returned None for {p.name}")
        except Exception as e:
            logger.warning(f"⚠️  Vision API failed for {p.name}: {type(e).__name__}: {e}")

        # Final identification: combine EXIF (1) + AI description (2) + Vision (3)
        file_exif = exif_metadata.get(p.name, {})
        logger.info(
            f"🔍 Calling identify_from_web_results for {p.name}: "
            f"web_results={'present' if web_results else 'None'}, "
            f"exif={'present' if file_exif else 'None'}"
        )
        try:
            identification = identify_from_web_results(
                web_results=web_results or {},
                image_description=welcome_message,
                exif_metadata=file_exif if file_exif else None,
            )
            if identification and identification.get("identified_name"):
                enrichment["identified_name"] = identification["identified_name"]
                enrichment["identification"] = identification
                logger.info(f"✅ Identified {p.name}: {identification['identified_name']}")
            else:
                logger.info(f"⚠️  No identification for {p.name}: {identification}")
        except Exception as e:
            logger.warning(f"⚠️  LLM identification failed for {p.name}: {type(e).__name__}: {e}")

        if enrichment:
            result[p.name] = enrichment
            logger.info(f"🔍 Enrichment for {p.name}: {list(enrichment.keys())}")
        else:
            logger.info(f"🔍 No enrichment produced for {p.name}")

    logger.info(f"🔍 enrich_metadata_web final result: {len(result)} files enriched")
    return result
