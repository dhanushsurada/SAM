"""
Compatibility forwarding layer — Phase 3A.5 architecture migration.

The real implementation moved to interfaces/api/gateway.py. TaskGateway
wires the phone-task HTTP API to SAM Core (Identity / MemoryRetriever /
FounderModeManager / Brain / ReactLoop) exactly as before — this is the API
interface's own orchestration, not something other interfaces (e.g.
Telegram) reuse, which is why it lives under interfaces/api/ rather than a
generic "core" location. This module re-exports the same objects so
`import iqoo.gateway` keeps working for anything outside this repo that
still references the old path. There is no separate implementation here.

New code should import from interfaces.api.gateway directly.
"""
from interfaces.api.gateway import (  # noqa: F401
    DEFAULT_TASK_TIMEOUT_SECONDS,
    TaskAlreadyActiveError,
    DemoResetBusyError,
    TaskGateway,
)

__all__ = [
    "DEFAULT_TASK_TIMEOUT_SECONDS",
    "TaskAlreadyActiveError",
    "DemoResetBusyError",
    "TaskGateway",
]
