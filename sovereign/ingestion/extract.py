"""
Format detection + text extraction: file bytes -> ExtractedDocument.

Supported types: PDF, DOCX, TXT, common images (png/jpg/jpeg/webp).
Stops at extraction — normalization/chunking is chunk.py's job, so this
module has exactly one responsibility: get faithful text + provenance
out of a single local file.

Provenance note: PDF pages are true pages (from the file format itself).
DOCX has no native pagination (pagination is a rendering-time concept,
not stored in the .docx XML), so "sections" are derived from heading
paragraphs instead — the closest meaningful analog for citation purposes.
TXT is treated as a single section; chunk.py subdivides it regardless.
"""

import base64
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import requests
from pypdf import PdfReader
import docx  # python-docx

logger = logging.getLogger("SAM.Sovereign.Ingestion")

SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
}


class ExtractionError(Exception):
    """Raised for any extraction failure (corrupt file, unreadable
    format, unreachable vision model, ...) so callers can catch one
    clean exception type regardless of which underlying library raised."""


@dataclass
class ExtractedPage:
    index: int       # 1-based
    label: str       # e.g. "page 3", "Inspection Checklist", "image"
    text: str


@dataclass
class ExtractedDocument:
    filename: str
    file_type: str
    content_hash: str  # sha256 hex digest of the raw file bytes
    pages: List[ExtractedPage] = field(default_factory=list)


def detect_file_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(set(SUPPORTED_EXTENSIONS.values())))
        raise ExtractionError(
            f"Unsupported file type '{ext}' for {path.name} — supported: {supported}"
        )
    return SUPPORTED_EXTENSIONS[ext]


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extract_pdf(path: Path) -> List[ExtractedPage]:
    try:
        reader = PdfReader(str(path))
    except Exception as e:
        raise ExtractionError(f"Could not open {path.name} as a PDF: {e}") from e

    pages = []
    for i, p in enumerate(reader.pages, start=1):
        try:
            text = p.extract_text() or ""
        except Exception as e:
            # A single bad page shouldn't sink the whole document — keep
            # it as an empty page rather than losing its slot in the
            # provenance chain.
            logger.warning("Page %d of %s failed to extract: %s", i, path.name, e)
            text = ""
        pages.append(ExtractedPage(index=i, label=f"page {i}", text=text))
    return pages


def _extract_docx(path: Path) -> List[ExtractedPage]:
    try:
        document = docx.Document(str(path))
    except Exception as e:
        raise ExtractionError(f"Could not open {path.name} as a DOCX: {e}") from e

    sections: List[ExtractedPage] = []
    current_label = "Document"
    current_lines: List[str] = []
    section_index = 0

    def _flush():
        nonlocal section_index
        text = "\n".join(current_lines).strip()
        if text:
            section_index += 1
            sections.append(ExtractedPage(index=section_index, label=current_label, text=text))

    for para in document.paragraphs:
        style = (para.style.name if para.style else "") or ""
        if style.startswith("Heading") and para.text.strip():
            _flush()
            current_label = para.text.strip()
            current_lines = []
        else:
            if para.text.strip():
                current_lines.append(para.text)
    _flush()

    if not sections:
        # No headings and no body paragraphs found at all — still a
        # valid (empty) document, not an error.
        sections.append(ExtractedPage(index=1, label="Document", text=""))
    return sections


def _extract_txt(path: Path) -> List[ExtractedPage]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    return [ExtractedPage(index=1, label="text", text=text)]


def _extract_image(path: Path, ollama_host: str, vision_model: str) -> List[ExtractedPage]:
    try:
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception as e:
        raise ExtractionError(f"Could not read image {path.name}: {e}") from e

    prompt = (
        "Transcribe all readable text from this image exactly as it "
        "appears. If there is no readable text, briefly describe the "
        "image instead."
    )
    try:
        resp = requests.post(
            f"{ollama_host}/api/generate",
            json={"model": vision_model, "prompt": prompt, "images": [b64], "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")
    except Exception as e:
        raise ExtractionError(
            f"Vision model call failed for {path.name} ({vision_model} via {ollama_host}): {e}"
        ) from e

    return [ExtractedPage(index=1, label="image", text=text)]


def extract(
    path: str,
    ollama_host: str = "http://localhost:11434",
    vision_model: str = "moondream",
) -> ExtractedDocument:
    """Detects type and extracts text + provenance from a single local
    file. Raises ExtractionError / FileNotFoundError / IsADirectoryError
    / ValueError on missing, malformed, unsupported, or empty input —
    never returns a partial/garbage result silently."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No such file: {path}")
    if p.is_dir():
        raise IsADirectoryError(f"Expected a file, got a directory: {path}")

    raw = p.read_bytes()
    if len(raw) == 0:
        raise ExtractionError(f"{p.name} is empty (0 bytes) — nothing to ingest")

    file_type = detect_file_type(p)
    content_hash = _hash_bytes(raw)

    if file_type == "pdf":
        pages = _extract_pdf(p)
    elif file_type == "docx":
        pages = _extract_docx(p)
    elif file_type == "txt":
        pages = _extract_txt(p)
    elif file_type == "image":
        pages = _extract_image(p, ollama_host=ollama_host, vision_model=vision_model)
    else:
        raise ExtractionError(f"No extractor wired up for detected type '{file_type}'")

    return ExtractedDocument(
        filename=p.name, file_type=file_type, content_hash=content_hash, pages=pages
    )
