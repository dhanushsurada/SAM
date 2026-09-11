"""
OFFLINE test suite — Phase 4.2, installer .venv idempotency.

Phase 4.1 design item F/P0: running setup.sh (or setup_linux.sh) a second
time must reuse a valid existing .venv rather than blindly recreating it,
and must repair (recreate) one that looks incomplete.

This test does NOT reimplement that logic in Python — a reimplementation
could silently drift from the real script and pass while the actual
installer regresses. Instead it extracts the literal bash lines between two
stable anchor comments directly from each real installer file and executes
them for real, in a throwaway temp directory. `python3 -m venv` needs no
network, so the actual venv-creation path is genuinely exercised, not
mocked — only the (network-dependent) Ollama/model/pip-upgrade steps
before and after this block are excluded from the extract.

Covers both setup.sh (macOS) and setup_linux.sh, since they share this
block near-verbatim — a regression in either is caught.

Never touches ~/.sam_data or the real HOME. All work happens in a
tempfile.TemporaryDirectory().

Usage:
    python3 tests/test_installer_venv_idempotency_offline.py
"""

import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
results = []

START_MARKER = "Creating Python virtual environment"
END_MARKER = "source .venv/bin/activate"

# setup_linux.sh detects $PYTHON once in step [1/8] and reuses it in step
# [5/8]'s venv block (setup.sh instead redetects it locally inside the venv
# block itself — the two scripts made different, both-reasonable choices
# here). Extracting step 5 alone from setup_linux.sh would leave $PYTHON
# unset and fail for a reason that has nothing to do with venv idempotency.
# This runs the real step-1 Python-detection prelude first so the test
# reflects each script's actual structure rather than assuming symmetry.
# The prelude is read-only detection (command -v checks) in this sandbox
# since python3 is already present — it never reaches the apt-get fallback.
PRELUDES = {
    "setup_linux.sh": ("Checking Python", "Checking PortAudio"),
}


def check(label, condition):
    results.append(bool(condition))
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")


def _extract_between(lines, start_text, end_text, filename):
    start = next((i for i, l in enumerate(lines) if start_text in l), None)
    end = next((i for i, l in enumerate(lines) if end_text in l), None)
    if start is None or end is None or end <= start:
        raise AssertionError(
            f"{filename}: could not locate a block between anchors "
            f"{start_text!r} and {end_text!r} — the script changed shape; "
            "update this test's anchors."
        )
    return lines[start + 1 : end]


def _extract_venv_block(installer_path: Path) -> str:
    """Pull the literal venv-reuse lines out of the real installer file,
    between the two stable anchor comments — plus, for scripts that need
    it, the real prelude that block actually depends on. Fails loudly if
    the anchors are gone, rather than silently testing nothing."""
    lines = installer_path.read_text().splitlines()
    chunks = []
    prelude = PRELUDES.get(installer_path.name)
    if prelude:
        chunks += _extract_between(lines, prelude[0], prelude[1], installer_path.name)
    chunks += _extract_between(lines, START_MARKER, END_MARKER, installer_path.name)
    return "\n".join(chunks)


def _run_block(installer_path: Path, workdir: Path) -> str:
    snippet = _extract_venv_block(installer_path)
    script = workdir / "_extracted_venv_block.sh"
    script.write_text("#!/bin/bash\nset -e\n" + snippet + "\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    result = subprocess.run(
        ["bash", str(script)], cwd=str(workdir),
        capture_output=True, text=True, timeout=60,
    )
    return result.stdout + result.stderr


def _make_fake_valid_venv(workdir: Path):
    """A .venv that already looks complete: has an executable bin/python3."""
    py = workdir / ".venv" / "bin" / "python3"
    py.parent.mkdir(parents=True)
    py.write_text("#!/bin/bash\necho fake\n")
    py.chmod(py.stat().st_mode | stat.S_IEXEC)
    sentinel = workdir / ".venv" / "sentinel.txt"
    sentinel.write_text("do-not-delete-me")
    return sentinel


def _is_real_venv(workdir: Path) -> bool:
    return (workdir / ".venv" / "bin" / "python3").exists() and \
           (workdir / ".venv" / "pyvenv.cfg").exists()


def _test_reuses_valid_venv(installer_path: Path):
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        sentinel = _make_fake_valid_venv(workdir)
        out = _run_block(installer_path, workdir)
        check(
            f"{installer_path.name}: reuses an existing valid .venv (doesn't recreate it)",
            "reusing it" in out,
        )
        check(
            f"{installer_path.name}: reused .venv's contents survive untouched",
            sentinel.exists() and sentinel.read_text() == "do-not-delete-me",
        )


def _test_repairs_incomplete_venv(installer_path: Path):
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        # Looks like a venv dir but has no bin/python3 — e.g. an interrupted
        # earlier install.
        (workdir / ".venv").mkdir()
        (workdir / ".venv" / "pyvenv.cfg").write_text("incomplete")
        out = _run_block(installer_path, workdir)
        check(
            f"{installer_path.name}: detects an incomplete .venv and recreates it",
            "recreating it" in out,
        )
        check(
            f"{installer_path.name}: incomplete .venv is replaced with a real, working venv",
            _is_real_venv(workdir),
        )


def _test_creates_fresh_venv(installer_path: Path):
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        out = _run_block(installer_path, workdir)
        check(
            f"{installer_path.name}: creates a real venv from nothing on first run",
            _is_real_venv(workdir),
        )


def main():
    print("=== Installer .venv idempotency (Phase 4.2) ===")
    for name in ("setup.sh", "setup_linux.sh"):
        installer_path = REPO_ROOT / name
        if not installer_path.exists():
            check(f"{name} exists", False)
            continue
        print(f"\n--- {name} ---")
        _test_creates_fresh_venv(installer_path)
        _test_reuses_valid_venv(installer_path)
        _test_repairs_incomplete_venv(installer_path)
    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("All installer venv-idempotency checks passed.")


if __name__ == "__main__":
    main()
