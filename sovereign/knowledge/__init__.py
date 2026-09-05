"""
Local document knowledge: a dedicated Chroma collection + citation-
preserving retrieval, built on top of sovereign/ingestion/'s Chunks.
"""

from .retrieval import RetrievalResult, search_knowledge
from .vector_index import VectorIndex, index_file

__all__ = ["RetrievalResult", "search_knowledge", "VectorIndex", "index_file"]
