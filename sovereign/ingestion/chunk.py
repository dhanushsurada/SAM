"""
Normalization + chunking: ExtractedDocument -> List[Chunk].

Chunking is word-based (not character-based) with a sliding overlap
window, which keeps chunks from splitting mid-word and is the common
baseline strategy for local RAG. doc_id is derived from the document's
content hash, so re-ingesting identical bytes deterministically produces
the same doc_id and chunk_ids — re-ingestion is naturally idempotent
once this feeds a vector index (Milestone 2), rather than silently
duplicating entries.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import List

from .extract import ExtractedDocument


@dataclass
class Chunk:
    chunk_id: str        # "{doc_id}:{section_index}:{chunk_index}"
    doc_id: str           # first 16 hex chars of the document's content hash
    filename: str
    file_type: str
    content_hash: str     # full sha256, kept alongside the shortened doc_id
    section: str           # page/section label, e.g. "page 3" or a DOCX heading
    section_index: int
    chunk_index: int       # 0-based, position of this chunk within its section
    text: str


def normalize(text: str) -> str:
    """Unicode-normalize and clean whitespace while preserving paragraph
    breaks, which carry some structure worth keeping for readability."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)          # collapse runs of spaces/tabs
    text = re.sub(r"\n{3,}", "\n\n", text)        # collapse 3+ blank lines to 1
    return text.strip()


def chunk_text(text: str, chunk_size: int = 300, chunk_overlap: int = 50) -> List[str]:
    """Word-based sliding-window chunking. chunk_size/chunk_overlap are
    word counts, not characters. Returns [] for empty/whitespace-only
    text, and a single chunk if the text is already short."""
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap must be >= 0, got {chunk_overlap}")
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) must be smaller than chunk_size ({chunk_size})"
        )

    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_size:
        return [" ".join(words)]

    chunks = []
    step = chunk_size - chunk_overlap
    for start in range(0, len(words), step):
        piece = words[start:start + chunk_size]
        if not piece:
            break
        chunks.append(" ".join(piece))
        if start + chunk_size >= len(words):
            break
    return chunks


def chunk_document(doc: ExtractedDocument, chunk_size: int = 300, chunk_overlap: int = 50) -> List[Chunk]:
    """Normalizes and chunks every page/section of an ExtractedDocument,
    attaching full provenance metadata to every chunk."""
    doc_id = doc.content_hash[:16]
    chunks: List[Chunk] = []
    for page in doc.pages:
        clean = normalize(page.text)
        pieces = chunk_text(clean, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        for i, piece in enumerate(pieces):
            chunks.append(Chunk(
                chunk_id=f"{doc_id}:{page.index}:{i}",
                doc_id=doc_id,
                filename=doc.filename,
                file_type=doc.file_type,
                content_hash=doc.content_hash,
                section=page.label,
                section_index=page.index,
                chunk_index=i,
                text=piece,
            ))
    return chunks
