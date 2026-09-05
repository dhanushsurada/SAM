"""
iQOO Hackathon 2026 competition branch — compatibility layer.

As of Phase 3A.5 (architecture migration), this package no longer holds
the real implementation. Everything that was generic SAM functionality
moved to its proper long-term home:

    iqoo/vision_adapter.py, audio_adapter.py, errors.py, media_validation.py
        -> multimodal/          (perception is a SAM capability, not iQOO-specific)

    iqoo/task_store.py, events.py, schemas.py, gateway.py, server.py
        -> interfaces/api/      (the phone-task HTTP+SSE interface)

Every module in this package is now a thin forwarding shim to one of those
locations, kept only so existing imports (`import iqoo.gateway`, etc.) and
`python -m iqoo.server` keep working without changes elsewhere. There is no
separate implementation left here — see docs/iqoo/PHASE_3A5_MIGRATION.md.

Nothing genuinely vivo/iQOO-specific (vendor SDK, Office Kit API calls,
Bluetooth/LAN transports) exists in this codebase yet. When it does, it
belongs under connect/bridges/vivo_iqoo/, not here.

New code should import directly from multimodal/ or interfaces/api/.
"""
