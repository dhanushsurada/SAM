"""
Local document vector index — a dedicated ChromaDB collection
(settings.sovereign_knowledge_collection, "sam_documents" by default)
kept separate from memory's "sam_memory" collection so conversational
memory and document evidence never mix.

Reuses the same on-disk Chroma directory as memory/store.py
(settings.chroma_path) — one persistent store, two collections, not a
second vector database. Same lazy try/except ImportError pattern as
memory/store.py._init_chroma(), for the same reason: this module must
stay importable even where chromadb isn't installed.

The Chroma client can be injected (client=...) for testing without the
chromadb package present — production code leaves it unset and this
builds a real chromadb.PersistentClient.
"""

import logging
from pathlib import Path
from typing import List, Optional

from core.embeddings import get_embedding
from sovereign.ingestion.chunk import Chunk

logger = logging.getLogger("SAM.Sovereign.Knowledge")


class VectorIndex:
    def __init__(self, settings, client=None):
        self.settings = settings
        self._collection = None

        if client is not None:
            self._collection = client.get_or_create_collection(
                name=settings.sovereign_knowledge_collection,
                metadata={"hnsw:space": "cosine"},
            )
            return

        try:
            import chromadb
            chroma_path = Path(settings.chroma_path)
            chroma_path.mkdir(parents=True, exist_ok=True)
            real_client = chromadb.PersistentClient(path=str(chroma_path))
            self._collection = real_client.get_or_create_collection(
                name=settings.sovereign_knowledge_collection,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                f"Document vector index at {chroma_path} "
                f"(collection={settings.sovereign_knowledge_collection})"
            )
        except ImportError:
            logger.warning("ChromaDB not installed — document knowledge retrieval unavailable")
        except Exception as e:
            logger.error(f"Vector index init error: {e}")

    @property
    def available(self) -> bool:
        return self._collection is not None

    def add_chunks(self, chunks: List[Chunk]) -> int:
        """Embeds and upserts chunks. upsert (not add) so re-ingesting an
        unchanged file — same deterministic chunk_ids, see
        sovereign/ingestion/chunk.py — replaces rather than duplicates or
        errors. Returns the number of chunks written; 0 if the index
        isn't available or there's nothing to add."""
        if not self.available or not chunks:
            return 0
        embeddings = [
            get_embedding(c.text, self.settings.ollama_host, self.settings.embedding_model)
            for c in chunks
        ]
        self._collection.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=[{
                "doc_id": c.doc_id,
                "filename": c.filename,
                "file_type": c.file_type,
                "content_hash": c.content_hash,
                "section": c.section,
                "section_index": c.section_index,
                "chunk_index": c.chunk_index,
            } for c in chunks],
        )
        return len(chunks)

    def query(self, query_text: str, top_k: int = 5) -> dict:
        """Returns raw Chroma-shaped results for retrieval.py to
        translate — kept separate so this class only knows about Chroma,
        not about the agent-facing result shape."""
        empty = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        if not self.available:
            return empty
        count = self._collection.count()
        if count == 0:
            return empty
        safe_k = min(top_k, count)
        embedding = get_embedding(query_text, self.settings.ollama_host, self.settings.embedding_model)
        return self._collection.query(
            query_embeddings=[embedding],
            n_results=safe_k,
            include=["documents", "metadatas", "distances"],
        )


def index_file(path: str, settings, index: Optional[VectorIndex] = None) -> int:
    """Convenience: ingest a local file and add its chunks to the
    document knowledge index in one call. Returns the number of chunks
    written. Builds a VectorIndex from settings if one isn't passed in.
    This is the local Python API only — making the agent able to call
    this itself is Milestone 3 (feat/agent-document-tools)."""
    from sovereign.ingestion import ingest_with_settings
    if index is None:
        index = VectorIndex(settings)
    chunks = ingest_with_settings(path, settings)
    return index.add_chunks(chunks)
