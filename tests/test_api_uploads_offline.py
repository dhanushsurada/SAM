"""
Offline test for api/uploads.py (M8-A).

No fastapi import — save_uploaded_file() accepts anything with
.filename/.file, so a plain stand-in object exercises the real
validation and file-writing logic without fastapi's UploadFile.

Usage:
    python3 tests/test_api_uploads_offline.py
"""

import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api import uploads as uploads_mod  # noqa: E402
from api.uploads import UploadValidationError, save_uploaded_file  # noqa: E402

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


class FakeUpload:
    def __init__(self, filename, content: bytes):
        self.filename = filename
        self.file = io.BytesIO(content)


def _tmp_dir():
    return tempfile.mkdtemp()


def _expect_rejected(upload, dest_dir, label):
    try:
        save_uploaded_file(upload, dest_dir)
        check(label, False)
    except UploadValidationError:
        check(label, True)


# ─── rejections ─────────────────────────────────────────────────────────

_expect_rejected(FakeUpload("", b"hello"), _tmp_dir(), "empty filename is rejected")
_expect_rejected(FakeUpload("report.exe", b"hello"), _tmp_dir(), "unsupported extension is rejected")
_expect_rejected(FakeUpload("../../etc/passwd.pdf", b"hello"), _tmp_dir(), "path traversal in filename is rejected")
_expect_rejected(FakeUpload("sub/dir/report.pdf", b"hello"), _tmp_dir(), "embedded path separator is rejected")
_expect_rejected(FakeUpload("report\x00.pdf", b"hello"), _tmp_dir(), "null byte in filename is rejected")
_expect_rejected(FakeUpload("report\n.pdf", b"hello"), _tmp_dir(), "control character in filename is rejected")
_expect_rejected(FakeUpload("empty.pdf", b""), _tmp_dir(), "zero-byte upload is rejected")
_expect_rejected(FakeUpload(".pdf", b"hello"), _tmp_dir(), "extension-only filename ('.pdf') is rejected")

# oversized: temporarily shrink the module's limit rather than generate a
# real 25MB blob, so the test stays fast — restored immediately after.
_original_max = uploads_mod.MAX_UPLOAD_BYTES
uploads_mod.MAX_UPLOAD_BYTES = 10
_expect_rejected(FakeUpload("big.txt", b"x" * 1000), _tmp_dir(), "oversized upload is rejected")
dest = _tmp_dir()
try:
    save_uploaded_file(FakeUpload("big.txt", b"x" * 1000), dest)
except UploadValidationError:
    pass
check("rejected oversized upload leaves no partial file behind", list(Path(dest).glob("*")) == [])
uploads_mod.MAX_UPLOAD_BYTES = _original_max


# ─── acceptance + safety of the stored result ─────────────────────────────

dest = _tmp_dir()
saved = save_uploaded_file(FakeUpload("Inspection Report (Final).pdf", b"%PDF-1.4 fake content"), dest)
check("a valid PDF upload is accepted", saved.exists())
check("stored file lives inside the destination directory", Path(dest).resolve() in saved.resolve().parents)
check("original display name (sanitized) is preserved in the stored filename",
      "Inspection Report _Final_" in saved.name)
check("the original extension is preserved", saved.suffix == ".pdf")
check("stored content matches what was uploaded", saved.read_bytes() == b"%PDF-1.4 fake content")

dest2 = _tmp_dir()
saved_a = save_uploaded_file(FakeUpload("same_name.txt", b"first"), dest2)
saved_b = save_uploaded_file(FakeUpload("same_name.txt", b"second"), dest2)
check("two uploads with the identical original filename never collide",
      saved_a != saved_b and saved_a.exists() and saved_b.exists())
check("both same-named uploads kept their distinct real content",
      saved_a.read_bytes() == b"first" and saved_b.read_bytes() == b"second")

for ext in (".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".webp"):
    d = _tmp_dir()
    p = save_uploaded_file(FakeUpload(f"file{ext}", b"content"), d)
    check(f"every M1-supported extension ({ext}) is accepted", p.exists())


if __name__ == "__main__":
    total = len(results)
    passed = sum(results)
    print(f"\n{passed}/{total} checks passed.")
    if passed != total:
        sys.exit(1)
    print("VEDA API upload validation (M8-A) verified.")
