"""
SAM Connect Core — device/trust abstractions.

    device_registry.py   Which remote devices are trusted, and pairing-token lifecycle

Formerly ecosystem/device_registry.py, relocated in Phase 3A.5. See
docs/iqoo/PHASE_3A5_MIGRATION.md.
"""
from .device_registry import DeviceRegistry

__all__ = ["DeviceRegistry"]
