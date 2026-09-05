"""
Compatibility forwarding layer — Phase 3A.5 architecture migration.

The real implementation moved to multimodal/media_validation.py (attachment
validation is a generic SAM capability, not iQOO-specific). This module
re-exports the same objects so `import iqoo.media_validation` keeps working
for anything outside this repo that still references the old path. There is
no separate implementation here.

New code should import from multimodal.media_validation directly.
"""
from multimodal.media_validation import (  # noqa: F401
    MAX_IMAGE_BYTES,
    MAX_AUDIO_BYTES,
    ALLOWED_IMAGE_MIME,
    ALLOWED_AUDIO_MIME,
    AUDIO_MIME_SUFFIX,
    AttachmentValidationError,
    validate_attachment,
)

__all__ = [
    "MAX_IMAGE_BYTES",
    "MAX_AUDIO_BYTES",
    "ALLOWED_IMAGE_MIME",
    "ALLOWED_AUDIO_MIME",
    "AUDIO_MIME_SUFFIX",
    "AttachmentValidationError",
    "validate_attachment",
]
