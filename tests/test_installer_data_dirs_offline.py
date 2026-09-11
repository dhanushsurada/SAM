"""
OFFLINE test suite — Phase 4.2, canonical ~/.sam_data initialization.

Phase 4.1 design item I / P0 constraint: installers must never overwrite or
delete ~/.sam_data, and must be safe to run twice. config/settings.py's
_ensure_data_dirs() is the actual mechanism this relies on (it runs at
module import time — see config/settings.py). This test exercises that
real function, not a reimplementation of it.

Each case runs a fresh `python3 -c "import config.settings"` subprocess
under an isolated HOME (config.settings.SAM_DATA_DIR is fixed at first
import, so this must be a fresh process per case — same reasoning as
test_runtime_config_offline.py and test_installer_doctor_model_check_offline.py).

Never touches the real ~/.sam_data.

Usage:
    python3 tests/test_installer_data_dirs_offline.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
results = []

EXPECTED_DIRS = [
    "",  # SAM_DATA_DIR itself
    "memory/chroma",
    "founder_mode",
    "founder_mode/export",
    "skills/compiled",
    "logs",
]


def check(label, condition):
    results.append(bool(condition))
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")


def _import_settings(home: Path):
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=str(REPO_ROOT),
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise AssertionError(f"import config.settings failed:\n{result.stderr}")


def test_first_run_creates_all_expected_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        _import_settings(home)
        sam_data = home / ".sam_data"
        for rel in EXPECTED_DIRS:
            d = sam_data / rel if rel else sam_data
            check(f"first run creates {d.relative_to(home)}", d.is_dir())


def test_rerun_does_not_touch_existing_user_data():
    """Simulates running the installer a second time against an existing
    installation: real files the user cares about must survive untouched."""
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        _import_settings(home)  # first run creates the structure

        sam_data = home / ".sam_data"
        user_settings = sam_data / "settings.yaml"
        user_settings.write_text("user_name: Dhanush\nassistant_name: SAM\n")
        memory_file = sam_data / "memory" / "chroma" / "collection.bin"
        memory_file.write_bytes(b"not-really-a-real-chroma-file-but-stands-in-for-one")
        founder_export = sam_data / "founder_mode" / "export" / "2026-01-01.json"
        founder_export.write_text('{"exported": true}')

        _import_settings(home)  # simulated installer rerun

        check(
            "rerun leaves user's settings.yaml untouched",
            user_settings.read_text() == "user_name: Dhanush\nassistant_name: SAM\n",
        )
        check(
            "rerun leaves memory data untouched",
            memory_file.exists() and memory_file.read_bytes() ==
            b"not-really-a-real-chroma-file-but-stands-in-for-one",
        )
        check(
            "rerun leaves founder_mode export untouched",
            founder_export.exists() and founder_export.read_text() == '{"exported": true}',
        )


def test_rerun_is_idempotent_no_duplicate_or_error():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        _import_settings(home)
        try:
            _import_settings(home)
            ok = True
        except AssertionError:
            ok = False
        check("running the initialization twice in a row raises no error", ok)


def main():
    print("=== Canonical ~/.sam_data initialization (Phase 4.2) ===")
    test_first_run_creates_all_expected_dirs()
    test_rerun_does_not_touch_existing_user_data()
    test_rerun_is_idempotent_no_duplicate_or_error()
    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("All canonical data-directory checks passed.")


if __name__ == "__main__":
    main()
