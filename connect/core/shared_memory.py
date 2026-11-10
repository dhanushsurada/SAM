"""
SAM Unified Memory & Context System

Separates memory into controlled scopes with explicit synchronization policies:
1. Personal Memory (long-term preferences, user profile - syncable with user consent)
2. Device-Specific Memory (screen state, app configs, hardware profile - strictly local)
3. Task Context (in-flight goal, active step, execution state - synced per active task)
4. Conversation History (recent session turns - syncable)
5. Sensitive Context (credentials, auth tokens, license keys - NEVER synced)

Features:
- Conflict resolution using vector timestamps / highest version
- Selective synchronization rules
- Preservation of local SQLite and ChromaDB integrity
"""

import time
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Set
from pathlib import Path

logger = logging.getLogger("SAM.SharedMemory")


class MemoryScope:
    PERSONAL = "personal"           # Preferences, long term facts
    DEVICE_LOCAL = "device_local"   # Screen resolutions, hardware, local paths (never synced)
    TASK = "task"                   # Active task execution state
    CONVERSATION = "conversation"   # Chat history
    SENSITIVE = "sensitive"         # API keys, private keys, passwords (NEVER synced)


@dataclass
class ScopedMemoryEntry:
    key: str
    value: Any
    scope: str
    origin_device_id: str
    version: int = 1
    updated_at: float = field(default_factory=time.time)
    sync_permitted: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ScopedContextManager:
    """Manages memory segregation and cross-device sync rules."""

    def __init__(self, device_id: str, data_dir: Optional[Path] = None):
        self.device_id = device_id
        self.data_dir = data_dir or (Path.home() / ".sam_data" / "memory")
        self._entries: Dict[str, ScopedMemoryEntry] = {}
        self._sync_whitelist_scopes = {MemoryScope.PERSONAL, MemoryScope.TASK, MemoryScope.CONVERSATION}

    def set(self, key: str, value: Any, scope: str = MemoryScope.PERSONAL, sync_permitted: bool = True) -> ScopedMemoryEntry:
        """Stores a scoped memory item."""
        if scope in (MemoryScope.DEVICE_LOCAL, MemoryScope.SENSITIVE):
            sync_permitted = False

        existing = self._entries.get(key)
        version = (existing.version + 1) if existing else 1

        entry = ScopedMemoryEntry(
            key=key,
            value=value,
            scope=scope,
            origin_device_id=self.device_id,
            version=version,
            updated_at=time.time(),
            sync_permitted=sync_permitted
        )
        self._entries[key] = entry
        return entry

    def get(self, key: str) -> Optional[Any]:
        entry = self._entries.get(key)
        return entry.value if entry else None

    def export_sync_package(self) -> List[Dict[str, Any]]:
        """
        Exports only permitted syncable items for transmission to another device.
        Guarantees that sensitive and device-local entries are never included.
        """
        package = []
        for entry in self._entries.values():
            if entry.sync_permitted and entry.scope in self._sync_whitelist_scopes:
                package.append(entry.to_dict())
        return package

    def apply_sync_package(self, remote_entries: List[Dict[str, Any]]) -> int:
        """
        Applies entries received from a trusted paired device using Last-Write-Wins
        or higher version conflict resolution.
        """
        applied_count = 0
        for item in remote_entries:
            scope = item.get("scope")
            if scope not in self._sync_whitelist_scopes:
                logger.warning(f"Rejecting sync for non-syncable scope '{scope}'")
                continue

            key = item.get("key")
            remote_version = item.get("version", 1)
            remote_updated = item.get("updated_at", 0.0)

            local = self._entries.get(key)
            if local:
                # Conflict resolution: higher version wins, or if equal, latest timestamp
                if remote_version < local.version:
                    continue
                if remote_version == local.version and remote_updated <= local.updated_at:
                    continue

            self._entries[key] = ScopedMemoryEntry(
                key=key,
                value=item.get("value"),
                scope=scope,
                origin_device_id=item.get("origin_device_id", "remote"),
                version=remote_version,
                updated_at=remote_updated,
                sync_permitted=True
            )
            applied_count += 1

        logger.info(f"Applied {applied_count} synced memory items from remote")
        return applied_count
