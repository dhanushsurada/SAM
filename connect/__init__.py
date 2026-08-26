"""
SAM Connect — how SAM communicates WITH DEVICES and external ecosystems.

    connect/core/       Device/trust abstractions (device_registry.py today)
    connect/bridges/     Manufacturer/ecosystem-specific adapters (e.g. vivo_iqoo/)

Not yet populated (nothing in the current codebase justifies them):
    connect/transports/  LAN / Bluetooth / future low-level transports
    connect/direct/      SAM Direct connectivity
    connect/services/    File transfer, clipboard, notifications, camera, screen, task handoff

SAM Core must never import from connect/ or from any manufacturer bridge.
Interfaces may depend on connect/ when they need device-related
functionality (interfaces/telegram/ depends on connect/core/device_registry.py
for trust checks) — that dependency direction is fine; the reverse is not.
"""
