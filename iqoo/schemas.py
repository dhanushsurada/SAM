"""
Compatibility forwarding layer — Phase 3A.5 architecture migration.

The real implementation moved to interfaces/api/schemas.py (the Pydantic
request/response contract for the phone-task HTTP API). This module
re-exports the same objects so `import iqoo.schemas` keeps working for
anything outside this repo that still references the old path. There is no
separate implementation here.

New code should import from interfaces.api.schemas directly.
"""
from interfaces.api.schemas import (  # noqa: F401
    InputType,
    Attachment,
    TaskCreateRequest,
    TaskRecord,
    ExecutionEvent,
    HealthStatus,
)

__all__ = [
    "InputType",
    "Attachment",
    "TaskCreateRequest",
    "TaskRecord",
    "ExecutionEvent",
    "HealthStatus",
]
