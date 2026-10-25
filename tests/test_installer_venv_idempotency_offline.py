"""
OFFLINE test suite — Phase 4.2, installer .venv idempotency.

Phase 4.1 design item F/P0: running setup.sh (or setup_linux.sh) a second
time must reuse a valid existing .venv rather than blindly recreating it,
and must repair (recreate) one that looks incomplete.

In modern SAM, virtual environment preparation is managed centrally by
`runtime/environment_manager.py prepare-venv`, invoked from setup.sh and
setup_linux.sh. This test verifies:
1. Both setup.sh and setup_linux.sh wire virtual environment preparation
   through the environment manager's `prepare-venv` command.
2. The environment manager creates a real, working virtual environment from scratch.
3. The environment manager reuses an existing valid .venv and preserves its contents.
4. An incomplete or corrupted .venv is detected, safely backed up, and replaced
   with a real working venv.

Never touches ~/.sam_data or the real HOME. All work happens in a
tempfile.TemporaryDirectory().

Usage:
    python3 tests/test_installer_venv_idempotency_offline.py
"""

import copy
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from runtime.compatibility import load_manifest
from runtime.environment_manager import EnvironmentCompatibilityManager

results = []


def check(label, condition):
    results.append(bool(condition))
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")


def _get_test_manager():
    manifest = copy.deepcopy(load_manifest())
    curr_v = f"{sys.version_info[0]}.{sys.version_info[1]}"
    if curr_v not in manifest["python"]["supported_versions"]:
        manifest["python"]["supported_versions"].append(curr_v)
    return EnvironmentCompatibilityManager(manifest=manifest)


def _is_real_venv(target: Path) -> bool:
    py = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    cfg = target / "pyvenv.cfg"
    return py.exists() and cfg.exists()


def _test_script_wires_prepare_venv(script_path: Path):
    content = script_path.read_text()
    check(
        f"{script_path.name}: invokes prepare-venv with --python and --path",
        "prepare-venv" in content and "--python" in content and "--path" in content,
    )


def _test_creates_fresh_venv():
    manager = _get_test_manager()
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / ".venv"
        out = manager.prepare_virtualenv(sys.executable, target)
        check(
            "creates a real venv from nothing on first run",
            out.get("created") is True and _is_real_venv(target),
        )


def _test_reuses_valid_venv():
    manager = _get_test_manager()
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / ".venv"
        out1 = manager.prepare_virtualenv(sys.executable, target)
        if not out1.get("created"):
            check("reuses an existing valid .venv (doesn't recreate it)", False)
            check("reused .venv's contents survive untouched", False)
            return

        sentinel = target / "sentinel.txt"
        sentinel.write_text("do-not-delete-me")

        out2 = manager.prepare_virtualenv(sys.executable, target)
        check(
            "reuses an existing valid .venv (doesn't recreate it)",
            out2.get("created") is False,
        )
        check(
            "reused .venv's contents survive untouched",
            sentinel.exists() and sentinel.read_text() == "do-not-delete-me",
        )


def _test_repairs_incomplete_venv():
    manager = _get_test_manager()
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / ".venv"
        target.mkdir(parents=True)
        (target / "pyvenv.cfg").write_text("incomplete")

        out = manager.prepare_virtualenv(sys.executable, target)
        check(
            "detects an incomplete .venv and recreates it",
            out.get("created") is True,
        )
        check(
            "incomplete .venv is replaced with a real, working venv",
            _is_real_venv(target),
        )
        backups = list(Path(tmp).glob(".venv.backup-*"))
        check(
            "incomplete .venv is backed up safely rather than silently lost",
            len(backups) > 0,
        )


def main():
    print("=== Installer .venv idempotency (Phase 4.2) ===")
    for name in ("setup.sh", "setup_linux.sh"):
        script_path = REPO_ROOT / name
        if not script_path.exists():
            check(f"{name} exists", False)
            continue
        _test_script_wires_prepare_venv(script_path)

    print("\n--- venv lifecycle & idempotency ---")
    _test_creates_fresh_venv()
    _test_reuses_valid_venv()
    _test_repairs_incomplete_venv()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("All installer venv-idempotency checks passed.")


if __name__ == "__main__":
    main()
