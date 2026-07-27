"""
Session — Manages a single interaction with SAM.
Holds context, history, and handles post-session memory saving.
"""

import logging
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

logger = logging.getLogger("SAM.Session")


@dataclass
class Session:
    user_input: str
    identity: Dict[str, Any]
    memories: List[Dict]
    founder_context: str
    settings: Any
    history: List[Dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def save(self, user_input: str, response, memory_store=None):
        """
        Extract and save memory from this interaction.
        Skipped entirely in incognito mode.

        memory_store: pass the already-cached MemoryStore (e.g. from
        MemoryRetriever.get_store()) to reuse the SAME SQLite/ChromaDB
        connection this turn's retrieve() call already opened, instead of
        creating a brand new one here. Confirmed via real Mac logs: every
        turn was opening a fresh SQLite connection AND re-initializing
        ChromaDB from scratch on save — real, measurable overhead on every
        single turn, worse on the slower hardware this project actually
        targets. Omit memory_store to get the old behaviour unchanged
        (creates its own store, exactly as before) — kept for backward
        compatibility with any caller not yet passing one.
        """
        if self.settings.incognito:
            logger.info("Incognito mode — session not saved")
            return

        try:
            if memory_store is not None:
                store = memory_store
            else:
                from memory.store import MemoryStore
                store = MemoryStore(self.settings)

            # Save episodic event
            store.save_episode(
                user_input=user_input,
                response=response.text,
                action=response.action,
                timestamp=self.created_at
            )

            # Extract and save semantic memory
            store.extract_and_save(
                user_input=user_input,
                response=response.text
            )

            logger.info("Session saved to memory")

        except Exception as e:
            logger.error(f"Session save error: {e}", exc_info=True)
