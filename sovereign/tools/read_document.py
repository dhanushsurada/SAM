"""
read_document() agent tool.

Reads one local file in full and returns its text, grouped by
page/section, wrapped as untrusted document content.

Uses sovereign.ingestion.extract() directly for the text the agent
reads — not the chunked/overlapping form — so the returned text has no
duplicated words at chunk boundaries. Chunking happens separately, only
for the indexing side effect: this also indexes the document into the
knowledge base (idempotent — see sovereign/ingestion/chunk.py's
deterministic chunk_ids) so a later search_knowledge() call can find it
without a separate explicit indexing step.

Long documents are truncated with a note pointing at search_knowledge
instead, rather than silently blowing up the context window.
"""

from pathlib import Path

from sovereign.ingestion import chunk_document, extract
from sovereign.security.document_trust import wrap_untrusted

MAX_CHARS = 8000


def read_document(path: str, settings, index=None) -> str:
    document = extract(
        path,
        ollama_host=settings.ollama_host,
        vision_model=settings.sovereign_vision_model or settings.vision_model,
    )

    if index is not None:
        chunks = chunk_document(
            document,
            chunk_size=settings.sovereign_chunk_size,
            chunk_overlap=settings.sovereign_chunk_overlap,
        )
        index.add_chunks(chunks)

    body_parts = [f"[{page.label}]\n{page.text}" for page in document.pages if page.text.strip()]
    full_text = "\n\n".join(body_parts) if body_parts else "(document contained no extractable text)"

    if len(full_text) > MAX_CHARS:
        remaining = len(full_text) - MAX_CHARS
        full_text = (
            f"{full_text[:MAX_CHARS]}\n\n"
            f"[...truncated, {remaining} more characters. Use search_knowledge "
            f"to find specific passages instead of reading the whole document.]"
        )

    return wrap_untrusted(full_text, source_label=document.filename)
