"""
Compatibility forwarding layer — Phase 3A.5 architecture migration.

The real implementation moved to connect/core/device_registry.py (device
trust/pairing is a SAM Connect concept per the finalized architecture, even
though today it's only wired up for the Telegram interface). This module
re-exports the same class so `import ecosystem.device_registry` keeps
working for anything outside this repo that still references the old path.
There is no separate implementation here.

New code should import from connect.core.device_registry directly.
"""
from connect.core.device_registry import (  # noqa: F401
    DeviceRegistry,
    SAM_DATA_DIR,
    ECOSYSTEM_DIR,
    DEVICES_DB_PATH,
    PAIRING_TOKEN_TTL_MINUTES,
)

__all__ = [
    "DeviceRegistry",
    "SAM_DATA_DIR",
    "ECOSYSTEM_DIR",
    "DEVICES_DB_PATH",
    "PAIRING_TOKEN_TTL_MINUTES",
]
