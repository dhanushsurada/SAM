"""
Compatibility forwarding layer — Phase 3A.5 architecture migration.

The real implementation moved to multimodal/errors.py (perception exceptions
are a generic SAM capability, not iQOO-specific). This module re-exports the
same objects so `import iqoo.errors` keeps working for anything outside this
repo that still references the old path. There is no separate
implementation here — these are the exact same classes, not copies.

New code should import from multimodal.errors directly.
"""
from multimodal.errors import PerceptionError, PerceptionCancelled  # noqa: F401

__all__ = ["PerceptionError", "PerceptionCancelled"]
