"""
SAM Telegram Interface — send SAM commands from your phone via Telegram.

    telegram_bridge.py   The bot process (long-polling, standalone)
    pair_new_device.py   One-time pairing QR code generator

Formerly ecosystem/telegram_bridge.py and ecosystem/pair_new_device.py,
relocated in Phase 3A.5 — Telegram is a SAM Interface/channel, not device
connectivity. See docs/iqoo/PHASE_3A5_MIGRATION.md.

Depends on connect/core/device_registry.py for device trust checks — an
Interface depending on SAM Connect for device-related functionality is the
sanctioned direction (the reverse, Connect depending on an Interface, is not).
"""
