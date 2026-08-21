"""
Memory Retrieval — Gets relevant memories for the current query.
"""

import logging
from typing import List, Dict

logger = logging.getLogger("SAM.MemoryRetriever")


class MemoryRetriever:
    def __init__(self):
        self._store = None

    def _get_store(self, settings=None):
        if self._store is None and settings:
            from memory.store import MemoryStore
            self._store = MemoryStore(settings)
        return self._store

    def get_store(self, settings=None):
        """
        Public accessor for the cached MemoryStore. Added so Session.save()
        can reuse the SAME instance retrieve() already created this turn,
        instead of constructing its own — see core/session.py for why this
        mattered (a real, confirmed performance bug: every turn was opening
        a brand new SQLite connection AND re-initializing ChromaDB from
        scratch on save, visible in every real Mac test log this whole
        project).
        """
        return self._get_store(settings)

    def retrieve(self, query: str, settings=None, top_k: int = 5, retention_days=None) -> List[Dict]:
        """
        retention_days: pass the free-tier cap (e.g. 7) to only surface
        memories from that window; omit (None) for unlimited.
        """
        try:
            store = self._get_store(settings)
            if store is None:
                return []

            # Guard: don't query if collection is empty
            if store._collection is None:
                return []

            count = store._collection.count()
            if count == 0:
                return []

            # Never request more than what exists
            safe_k = min(top_k, count)
            return store.search_semantic(query, top_k=safe_k, retention_days=retention_days)

        except Exception as e:
            logger.debug(f"Memory retrieval skipped: {e}")
            return []
