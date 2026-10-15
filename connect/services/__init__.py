"""
SAM Connect — Services

Reserved by connect/__init__.py ("File transfer, clipboard, notifications,
camera, screen, task handoff") and populated for the first time in
agent/cross-device, for the one item on that list this branch actually
implements:

    connect/services/task_handoff.py   Device task routing, lifecycle,
                                        idempotency, offline queueing,
                                        and cross-device context handoff.

The rest of the reserved list (file transfer, clipboard, notifications,
camera, screen) is real future scope, not implemented here — each would
be a capability name in connect/core/capabilities.py plus a routed
DeviceTask action, using the same task_handoff.py machinery, not a new
routing system per capability.
"""
