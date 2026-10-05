"""Document ingestion: text chunking and visual artifact extraction."""

import io
import logging
import os
import re
import uuid
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

# Auto-detect Tesseract on Windows if available in common locations
if os.name == "nt":
    for candidate in [
        os.environ.get("TESSERACT_CMD"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]:
        if candidate and Path(candidate).is_file():
            pytesseract.pytesseract.tesseract_cmd = candidate
            break

BASE_DIR = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = BASE_DIR / "static" / "artifacts"

# Defensive extraction thresholds: reject icons, bullets and divider lines.
MIN_ARTIFACT_DIMENSION = 150
MIN_ARTIFACT_ASPECT = 0.1
MAX_ARTIFACT_ASPECT = 10.0

SUPPORTED_EXTENSIONS = (".pdf", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp", ".bmp")


def ensure_artifact_dir() -> Path:
    """Create the artifact directory if it does not yet exist."""
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACT_DIR


def _build_chunk(text, file_name, location_tag, page_number=None):
    """Build the canonical chunk payload consumed by the graph engine."""
    return {
        "chunk_id": str(uuid.uuid4()),
        "text": text,
        "file_name": file_name,
        "location_tag": location_tag,
        "raw_snippet": text,
        "page_number": page_number,
    }


def chunk_text(text, chunk_size=3, overlap=1):
    """Split text into sentence windows of ``chunk_size`` with a sliding overlap."""
    clean_text = re.sub(r"\s+", " ", text or "").strip()
    if not clean_text:
        return []

    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?]) +", clean_text)
        if len(s.strip()) > 0
    ]
    if not sentences:
        sentences = [clean_text]
    if len(sentences) <= chunk_size:
        return [" ".join(sentences)]

    step = max(1, chunk_size - overlap)
    chunks = []
    index = 0
    while index < len(sentences):
        chunk = " ".join(sentences[index:index + chunk_size]).strip()
        if chunk and (not chunks or chunk != chunks[-1]):
            chunks.append(chunk)
        if index + chunk_size >= len(sentences):
            break
        index += step
    return chunks


def _is_valid_artifact(width, height) -> bool:
    """Filter out tiny icons, bullets and thin divider lines."""
    if width < MIN_ARTIFACT_DIMENSION or height < MIN_ARTIFACT_DIMENSION:
        return False
    if height <= 0:
        return False
    aspect = width / height
    return MIN_ARTIFACT_ASPECT <= aspect <= MAX_ARTIFACT_ASPECT


def _persist_artifact(image_bytes, artifact_id) -> Path:
    """Normalise arbitrary embedded image data to PNG on the local filesystem."""
    ensure_artifact_dir()
    destination = ARTIFACT_DIR / f"{artifact_id}.png"
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.convert("RGB").save(destination, format="PNG")
    return destination


def _build_artifact(artifact_id, file_name, location_tag, page_number=None, caption=None):
    return {
        "id": artifact_id,
        "file_name": file_name,
        "location_tag": location_tag,
        "page_number": page_number,
        "image_url": f"/static/artifacts/{artifact_id}.png",
        "caption": caption or f"Diagram from {location_tag}",
    }


def extract_artifacts(file_bytes, file_name):
    """Extract embedded diagrams/figures from a PDF as :Artifact payloads."""
    artifacts = []
    seen_xrefs = set()

    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:  # pragma: no cover - malformed upload
        logger.warning("Could not open '%s' for artifact extraction: %s", file_name, exc)
        return artifacts

    with doc:
        for page_index in range(len(doc)):
            page = doc[page_index]
            for image_info in page.get_images(full=True):
                xref = image_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                try:
                    raw = doc.extract_image(xref)
                except Exception as exc:
                    logger.debug("Skipping xref %s: %s", xref, exc)
                    continue

                width = raw.get("width", 0)
                height = raw.get("height", 0)
                if not _is_valid_artifact(width, height):
                    continue

                artifact_id = str(uuid.uuid4())
                try:
                    _persist_artifact(raw["image"], artifact_id)
                except Exception as exc:
                    logger.debug("Could not persist artifact xref %s: %s", xref, exc)
                    continue

                artifacts.append(
                    _build_artifact(
                        artifact_id,
                        file_name,
                        f"Page {page_index + 1}",
                        page_number=page_index + 1,
                    )
                )

    return artifacts


def parse_pdf(file_bytes, filename):
    """Extract page-scoped text chunks plus embedded visual artifacts."""
    chunks = []
    with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
        for page_index in range(len(doc)):
            page = doc[page_index]
            text = page.get_text("text").strip()
            for chunk in chunk_text(text):
                chunks.append(
                    _build_chunk(
                        chunk,
                        filename,
                        f"Page {page_index + 1}",
                        page_number=page_index + 1,
                    )
                )
    return chunks, extract_artifacts(file_bytes, filename)


def parse_txt(file_bytes, filename):
    """Extract text chunks from a plain-text or markdown upload."""
    text = file_bytes.decode("utf-8", errors="ignore").strip()
    chunks = [_build_chunk(chunk, filename, "Document Note") for chunk in chunk_text(text)]
    return chunks, []


def parse_image(file_bytes, filename):
    """OCR an uploaded image and register the image itself as a visual artifact."""
    text = ""
    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            text = pytesseract.image_to_string(image).strip()
    except pytesseract.TesseractNotFoundError:
        logger.warning(
            "Tesseract is not installed or not in PATH. OCR skipped for '%s'.", filename
        )
        raise ValueError(
            "Tesseract OCR is not installed or not found in system PATH. "
            "Please install Tesseract OCR to process standalone image uploads."
        )
    except Exception as exc:
        logger.warning("OCR failed for image '%s': %s", filename, exc)

    chunks = [_build_chunk(chunk, filename, "Image OCR") for chunk in chunk_text(text)]

    artifacts = []
    artifact_id = str(uuid.uuid4())
    try:
        _persist_artifact(file_bytes, artifact_id)
        artifacts.append(
            _build_artifact(
                artifact_id,
                filename,
                "Image OCR",
                caption=f"Uploaded image: {filename}",
            )
        )
    except Exception as exc:
        logger.warning("Could not persist uploaded image '%s': %s", filename, exc)

    return chunks, artifacts


PARSERS = {
    ".pdf": parse_pdf,
    ".txt": parse_txt,
    ".md": parse_txt,
    ".png": parse_image,
    ".jpg": parse_image,
    ".jpeg": parse_image,
    ".webp": parse_image,
    ".bmp": parse_image,
}


def parse_document(file_bytes, filename):
    """Dispatch an upload to the parser matching its extension."""
    extension = Path(filename or "").suffix.lower()
    parser = PARSERS.get(extension)
    if parser is None:
        raise ValueError(
            f"Unsupported file type '{extension or 'unknown'}'. "
            f"Allowed types: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    return parser(file_bytes, filename)
