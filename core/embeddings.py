"""
Shared local embedding helper — a single Ollama /api/embeddings call.

Used by memory/store.py (conversational semantic memory) and
sovereign/knowledge/vector_index.py (document knowledge, SIH26117).
Extracted here so both share one implementation instead of two
near-identical HTTP calls (previously duplicated in memory/store.py) —
see Section F of SIH26117_Repository_Audit.md.

Deliberately has no try/except of its own: it raises whatever
requests/json raises on failure, exactly as memory/store.py's original
inline version did, so existing callers' error handling is unaffected
by this extraction.
"""

import requests


def get_embedding(text: str, ollama_host: str, embedding_model: str) -> list:
    response = requests.post(
        f"{ollama_host}/api/embeddings",
        json={"model": embedding_model, "prompt": text},
        timeout=30,
    )
    return response.json()["embedding"]
