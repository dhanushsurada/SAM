"""
search_knowledge() agent tool.

Thin wrapper around sovereign/knowledge/'s search_knowledge(), formatted
into a readable, cited string and wrapped as untrusted document content
before it enters the agent's context.
"""

from sovereign.knowledge import search_knowledge as _search_knowledge
from sovereign.security.document_trust import wrap_untrusted


def search_knowledge(query: str, settings, index) -> str:
    if not index.available:
        return (
            "Document knowledge search is unavailable right now (no "
            "documents indexed yet, or the local vector store isn't "
            "reachable). Try read_document on a specific file instead."
        )

    top_k = getattr(settings, "sovereign_top_k", 5)
    found = _search_knowledge(query, index, top_k=top_k)
    if not found:
        return f"No relevant passages found for: {query}"

    parts = [
        f"[{r.filename} — {r.section}, relevance {r.relevance:.2f}]\n{r.text}"
        for r in found
    ]
    body = "\n\n".join(parts)
    return wrap_untrusted(body, source_label=f"{len(found)} passage(s) matching '{query}'")
