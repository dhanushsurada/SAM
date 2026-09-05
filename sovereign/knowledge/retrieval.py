"""
search_knowledge() — top-k semantic search over ingested documents,
returning content + source + section + a relevance score for every
result. This is the exact call shape Milestone 3 (feat/agent-document-
tools) will wire directly into the agent as the search_knowledge tool.
"""

from dataclasses import dataclass
from typing import List

from .vector_index import VectorIndex


@dataclass
class RetrievalResult:
    text: str
    filename: str
    section: str
    section_index: int
    doc_id: str
    relevance: float  # 0-1, higher is more relevant (1 - cosine distance, clamped)


def search_knowledge(query: str, index: VectorIndex, top_k: int = 5) -> List[RetrievalResult]:
    raw = index.query(query, top_k=top_k)
    docs = raw.get("documents") or [[]]
    metas = raw.get("metadatas") or [[]]
    dists = raw.get("distances") or [[]]

    results: List[RetrievalResult] = []
    if not docs or not docs[0]:
        return results

    for text, meta, dist in zip(docs[0], metas[0], dists[0]):
        meta = meta or {}
        results.append(RetrievalResult(
            text=text,
            filename=meta.get("filename", "unknown"),
            section=meta.get("section", "unknown"),
            section_index=meta.get("section_index", 0),
            doc_id=meta.get("doc_id", ""),
            relevance=max(0.0, min(1.0, 1 - dist)),
        ))
    return results
