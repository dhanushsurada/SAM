#!/usr/bin/env python3
"""Stage relocatable macOS runtime resources for the Tauri consumer bundle.

Run from any directory with uv and network access on the target architecture.
This is a packaging step; source-based setup remains independent of it.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "interfaces/desktop/src-tauri/resources/sam-runtime"
MANIFEST = json.loads((ROOT / "compatibility/manifest.json").read_text())
SOURCE_DIRS = (
    "agent", "config", "connect", "core", "ears", "ecosystem", "founder_mode",
    "hands", "iqoo", "licensing", "memory", "mouth", "multimodal", "runtime",
    "skills", "sovereign", "compatibility",
)


def run(args: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def main() -> int:
    if platform.system() != "Darwin":
        raise SystemExit("Consumer macOS packaging must run on macOS so native Python wheels match the target.")
    if platform.machine() not in MANIFEST["platforms"]["macos"]["architectures"]:
        raise SystemExit("This macOS architecture is outside compatibility/manifest.json.")
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv is required on the packaging machine. Install it with Homebrew (brew install uv), then retry.")
    version = MANIFEST["python"]["preferred_versions"][0]
    staging_parent = OUT.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sam-runtime-", dir=staging_parent) as temp:
        stage = Path(temp) / "sam-runtime"
        source = stage / "source"
        python_dir = stage / "python"
        site_packages = stage / "site-packages"
        source.mkdir(parents=True)
        python_dir.mkdir(parents=True)
        site_packages.mkdir(parents=True)
        for name in SOURCE_DIRS:
            shutil.copytree(ROOT / name, source / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests", ".git"))
        (source / "interfaces").mkdir(exist_ok=True)
        for name in ("api", "telegram"):
            origin = ROOT / "interfaces" / name
            if origin.exists():
                shutil.copytree(origin, source / "interfaces" / name,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests", ".git"))
        for name in ("__init__.py",):
            if (ROOT / "interfaces" / name).exists():
                shutil.copy2(ROOT / "interfaces" / name, source / "interfaces" / name)
        for name in ("sam_cli.py", "main.py", "requirements.txt"):
            shutil.copy2(ROOT / name, source / name)
        run([uv, "python", "install", "--install-dir", str(python_dir), version])
        candidates = [p for p in python_dir.rglob("python3.*") if p.is_file() and os.access(p, os.X_OK)]
        if not candidates:
            candidates = [p for p in python_dir.rglob("python") if p.is_file() and os.access(p, os.X_OK)]
        if not candidates:
            raise SystemExit("uv installed Python but no executable was found in the managed runtime directory.")
        interpreter = sorted(candidates, key=lambda p: len(str(p)))[0]
        alias = python_dir / "bin" / "python3"
        alias.parent.mkdir(parents=True, exist_ok=True)
        if not alias.exists():
            alias.symlink_to(interpreter)
        # Resolve the same declared core group used by the source installers.
        lines = subprocess.check_output(
            [sys.executable, str(ROOT / "runtime/environment_manager.py"),
             "resolve-dependencies", "--group", "core", "--format", "requirements"],
            cwd=ROOT, text=True,
        ).splitlines()
        run([uv, "pip", "install", "--python", str(alias), "--target", str(site_packages), *lines])
        metadata = {
            "runtime_layout": 1,
            "python_version": version,
            "architecture": platform.machine(),
            "dependency_groups": ["core"],
            "created_unix": int(time.time()),
            "optional_capabilities": "Install through SAM setup when capability package management is available.",
        }
        (stage / "bundle.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        if OUT.exists():
            backup = OUT.with_name("sam-runtime.previous-{}".format(time.strftime("%Y%m%d%H%M%S")))
            OUT.rename(backup)
        stage.rename(OUT)
    print("Staged macOS consumer resources at {}".format(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
