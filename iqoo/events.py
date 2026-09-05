"""
Compatibility forwarding layer — Phase 3A.5 architecture migration.

The real implementation moved to interfaces/api/events.py (the reconnect-safe
SSE bus for the phone-task HTTP API). This module re-exports the same
objects so `import iqoo.events` keeps working for anything outside this repo
that still references the old path. There is no separate implementation
here.

New code should import from interfaces.api.events directly.
"""
from interfaces.api.events import EventBus, TERMINAL_PHASES  # noqa: F401

__all__ = ["EventBus", "TERMINAL_PHASES"]
