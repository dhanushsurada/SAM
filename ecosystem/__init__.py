"""
Ecosystem — compatibility layer.

As of Phase 3A.5 (architecture migration), this package no longer holds
the real implementation. Everything that used to live here moved to its
proper long-term home:

    ecosystem/device_registry.py
        -> connect/core/device_registry.py   (SAM Connect — device trust/pairing)

    ecosystem/telegram_bridge.py, pair_new_device.py
        -> interfaces/telegram/              (Telegram is a SAM Interface, not
                                               device connectivity)

Every module in this package is now a thin forwarding shim to one of those
locations, kept only so existing imports (`import ecosystem.device_registry`,
etc.) and `python -m ecosystem.pair_new_device` / `python -m
ecosystem.telegram_bridge` keep working without changes elsewhere. There is
no separate implementation left here — see docs/iqoo/PHASE_3A5_MIGRATION.md.

The on-disk data directory is still named "ecosystem"
(~/.sam_data/ecosystem/devices.db) — moving the Python code does not move or
rename existing user data.

New code should import directly from connect.core or interfaces.telegram.
"""
from .device_registry import DeviceRegistry

__all__ = ["DeviceRegistry"]
