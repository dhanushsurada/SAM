"""
Upload validation + safe storage for the VEDA localhost API (M8-A).

No fastapi import — accepts any object with .filename (str) and .file
(a binary file-like with .read(n)), which is exactly the shape
fastapi's UploadFile has, but also exactly the shape a plain
io.BytesIO-backed stand-in has, so this module is directly testable
without fastapi installed.

There was never a network-facing upload surface in SAM before M8, so
none of this validation logic already exists elsewhere to "reuse" —
this is new, API-layer-owned code, not a duplication of engine logic.
What it does reuse is the actual M1 supported-extension list
(sovereign.ingestion.extract.SUPPORTED_EXTENSIONS), so "which file
types are supported" has exactly one source of truth in the codebase,
not two lists that could drift apart.
"""

import re
import uuid
from pathlib import Path
from typing import Any

from sovereign.ingestion.extract import SUPPORTED_EXTENSIONS

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB — generous for an inspection PDF/DOCX/photo, not unbounded
_READ_CHUNK = 1024 * 1024
_SAFE_STEM_RE = re.compile(r"[^A-Za-z0-9 _\-]")


class UploadValidationError(Exception):
    """Raised for any invalid upload. api/app.py maps this to HTTP 400 —
    it is never allowed to surface as an unhandled 500."""


def save_uploaded_file(upload: Any, dest_dir: str) -> Path:
    """
    Validates and safely persists one uploaded file under dest_dir.

    The client-supplied filename is NEVER used to build a filesystem
    path — only its extension is checked (against SUPPORTED_EXTENSIONS)
    and a regex-cleaned stem is kept purely for human readability. The
    actual on-disk name is <uuid>_<safe_stem><ext>, so two uploads can
    never collide or overwrite one another, and there is no way for a
    crafted filename to escape dest_dir.
    """
    raw_name = (getattr(upload, "filename", "") or "").strip()
    if not raw_name:
        raise UploadValidationError("No filename provided")

    # A filename containing a separator or a null byte isn't a
    # filename, it's a path — reject outright rather than "cleaning" it.
    if "/" in raw_name or "\\" in raw_name or "\x00" in raw_name or raw_name in (".", ".."):
        raise UploadValidationError("Invalid filename")
    if any(ord(c) < 32 for c in raw_name):
        raise UploadValidationError("Filename contains control characters")

    suffix = Path(raw_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(set(SUPPORTED_EXTENSIONS.values())))
        raise UploadValidationError(f"Unsupported file type '{suffix or '(none)'}' — supported: {supported}")

    stem = Path(raw_name).stem
    safe_stem = _SAFE_STEM_RE.sub("_", stem).strip() or "document"
    safe_stem = safe_stem[:80]

    dest_root = Path(dest_dir)
    dest_root.mkdir(parents=True, exist_ok=True)
    dest_root_resolved = dest_root.resolve()
    on_disk_name = f"{uuid.uuid4().hex[:12]}_{safe_stem}{suffix}"
    dest_path = (dest_root / on_disk_name).resolve()

    # Defense in depth: on_disk_name can't contain a separator (built
    # from a UUID + a regex-cleaned stem + a checked extension), but
    # confirm the resolved path is still actually inside dest_root
    # before writing anything, rather than trusting that by construction.
    if dest_root_resolved not in dest_path.parents:
        raise UploadValidationError("Resolved path escaped the upload directory")

    size = 0
    try:
        with open(dest_path, "wb") as f:
            while True:
                chunk = upload.file.read(_READ_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise UploadValidationError(
                        f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit"
                    )
                f.write(chunk)
    except UploadValidationError:
        dest_path.unlink(missing_ok=True)
        raise

    if size == 0:
        dest_path.unlink(missing_ok=True)
        raise UploadValidationError("Uploaded file is empty")

    return dest_path
