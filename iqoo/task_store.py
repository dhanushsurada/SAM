"""
Compatibility forwarding layer — Phase 3A.5 architecture migration.

The real implementation moved to interfaces/api/task_store.py (this is the
phone-task HTTP API's own storage component; it isn't shared with other
interfaces such as Telegram, which is why it lives under interfaces/api/
rather than a generic "core" location). This module re-exports the same
objects so `import iqoo.task_store` keeps working for anything outside this
repo that still references the old path. There is no separate
implementation here.

Note: the on-disk data directory is still named "iqoo"
(~/.sam_data/iqoo/tasks.db) — moving the Python code does not move or
rename existing user data.

New code should import from interfaces.api.task_store directly.
"""
from interfaces.api.task_store import (  # noqa: F401
    SAM_DATA_DIR,
    IQOO_DIR,
    TASKS_DB_PATH,
    ORPHAN_ERROR_MESSAGE,
    TERMINAL_STATUSES,
    ALL_STATUSES,
    TaskStore,
)

__all__ = [
    "SAM_DATA_DIR",
    "IQOO_DIR",
    "TASKS_DB_PATH",
    "ORPHAN_ERROR_MESSAGE",
    "TERMINAL_STATUSES",
    "ALL_STATUSES",
    "TaskStore",
]
