"""
SAM Connect — Transports

Reserved by connect/__init__.py ("LAN / Bluetooth / future low-level
transports") and populated for the first time in agent/cross-device.

    connect/transports/lan_http.py   Same-WiFi HTTP transport: the
                                      request-signing scheme, pairing
                                      payload, and offline-device
                                      heartbeat sweep that
                                      interfaces/api/connect_routes.py
                                      wires into FastAPI routes.

Only one transport exists today — signed HTTP over the same local
network the phone-task gateway already uses (see
connect/bridges/vivo_iqoo/README.md: "today's phone connectivity is
same-WiFi HTTP"). A future Bluetooth or SAM Direct transport would be a
sibling module here implementing the same device-authentication contract
(connect/core/device_registry.py + connect/core/crypto.py), not a
parallel trust system.
"""
