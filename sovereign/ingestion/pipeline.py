"""
Milestone 1 orchestration: file -> detect -> extract -> normalize -> chunk
-> metadata.

Deliberately stops here. No embedding, no indexing, no agent/Brain
wiring — those belong to later milestones (sovereign/knowledge/,
sovereign/tools/) so ingestion stays testable in complete isolation.
Only the image path needs a reachable Ollama host; pdf/docx/txt need
nothing beyond the local filesystem.
"""

import logging
from typing import List

from .chunk import Chunk, chunk_document
from .extract import extract

logger = logging.getLogger("SAM.Sovereign.Ingestion")


def ingest_file(
    path: str,
    chunk_size: int = 300,
    chunk_overlap: int = 50,
    ollama_host: str = "http://localhost:11434",
    vision_model: str = "moondream",
) -> List[Chunk]:
    """Runs one local file through the full ingestion pipeline and
    returns its chunks, each carrying full provenance (filename,
    content hash, page/section, chunk index). Raises on missing,
    unsupported, or corrupt files rather than returning a partial
    result silently — the future read_document tool (Milestone 3)
    decides how to translate that into an agent-facing message."""
    document = extract(path, ollama_host=ollama_host, vision_model=vision_model)
    chunks = chunk_document(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    logger.info(
        "Ingested %s (%s, %d pages/sections -> %d chunks)",
        document.filename, document.file_type, len(document.pages), len(chunks),
    )
    return chunks


def ingest_with_settings(path: str, settings) -> List[Chunk]:
    """Convenience wrapper that pulls chunk size/overlap/host/model from
    a config.settings.Settings instance instead of passing each value
    individually. This is the entry point later milestones should call."""
    return ingest_file(
        path,
        chunk_size=settings.sovereign_chunk_size,
        chunk_overlap=settings.sovereign_chunk_overlap,
        ollama_host=settings.ollama_host,
        vision_model=settings.sovereign_vision_model or settings.vision_model,
    )
