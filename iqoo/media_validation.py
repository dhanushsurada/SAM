"""
iQOO Phase 2 — Attachment validation.

Centralized here (rather than scattered inline in schemas.py) so the
same rules are testable directly and reusable if a second entry point
(e.g. a future multipart upload endpoint) is ever added.

Size limits are deliberately generous but finite: a phone camera JPEG
is typically 1-6MB; a voice clip a few minutes long, compressed, is
usually under 5MB. These limits exist to reject a mistaken/malicious
huge payload cleanly (PDR: "never silently discard an image", "reject
malformed uploads cleanly") — not to be a tight production quota.
"""

import base64

MAX_IMAGE_BYTES = 8 * 1024 * 1024   # 8 MB
MAX_AUDIO_BYTES = 15 * 1024 * 1024  # 15 MB

ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_AUDIO_MIME = {"audio/webm", "audio/wav", "audio/x-wav", "audio/mp4",
                       "audio/ogg", "audio/mpeg"}

# Used by iqoo/audio_adapter.py to pick a sensible temp-file suffix so
# faster-whisper's format sniffing (via PyAV) has a hint to work with.
AUDIO_MIME_SUFFIX = {
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".mp4",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
}


class AttachmentValidationError(ValueError):
    pass


def validate_attachment(kind: str, mime_type: str, b64_data: str) -> bytes:
    """Validates MIME type, base64 well-formedness, and size for a single
    attachment. Returns the decoded bytes on success (callers that only
    need to validate, like the Pydantic schema, can discard the return
    value). Raises AttachmentValidationError with a specific, honest
    reason on any failure — never fails silently."""
    if kind not in ("image", "audio"):
        raise AttachmentValidationError(f"Unknown attachment kind: {kind!r}")

    allowed = ALLOWED_IMAGE_MIME if kind == "image" else ALLOWED_AUDIO_MIME
    limit = MAX_IMAGE_BYTES if kind == "image" else MAX_AUDIO_BYTES

    if mime_type not in allowed:
        raise AttachmentValidationError(
            f"Unsupported {kind} MIME type {mime_type!r} — allowed: {sorted(allowed)}")

    if not b64_data:
        raise AttachmentValidationError(f"{kind} attachment has no data")

    try:
        raw = base64.b64decode(b64_data, validate=True)
    except Exception as e:
        raise AttachmentValidationError(f"{kind} attachment is not valid base64: {e}") from e

    if len(raw) == 0:
        raise AttachmentValidationError(f"{kind} attachment decoded to zero bytes")

    if len(raw) > limit:
        raise AttachmentValidationError(
            f"{kind} attachment too large: {len(raw)} bytes exceeds the {limit} byte limit")

    return raw
