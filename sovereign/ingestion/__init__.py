"""
Document ingestion: file -> detect -> extract -> normalize -> chunk -> metadata.

Stops before embedding/indexing on purpose — see sovereign/knowledge/
(a later milestone) — so this stage is testable in complete isolation.
"""

from .chunk import Chunk, chunk_document, chunk_text, normalize
from .extract import (
    ExtractedDocument,
    ExtractedPage,
    ExtractionError,
    detect_file_type,
    extract,
)
from .pipeline import ingest_file, ingest_with_settings

__all__ = [
    "Chunk",
    "chunk_document",
    "chunk_text",
    "normalize",
    "ExtractedDocument",
    "ExtractedPage",
    "ExtractionError",
    "detect_file_type",
    "extract",
    "ingest_file",
    "ingest_with_settings",
]
