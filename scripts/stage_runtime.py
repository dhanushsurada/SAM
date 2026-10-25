#!/usr/bin/env python3
"""Stage the relocatable SAM runtime that the Tauri consumer installers embed.

Runs on the *target* operating system and architecture (Windows, macOS or
Linux) because native Python wheels must match the machine that will run
them. CI runs it once per platform; a developer can run it locally.

Layout produced under ``interfaces/desktop/src-tauri/resources/sam-runtime``:

    source/           SAM application source (no tests, docs, GUI or Android)
    python/           Managed CPython (python/bin/python3 or python/python.exe)
    site-packages/    Core dependency group, installed with --target
    bundle.json       Runtime metadata consumed by the app and by smoke tests

Usage:
    python scripts/stage_runtime.py [--out DIR] [--skip-deps] [--no-verify]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "interfaces/desktop/src-tauri/resources/sam-runtime"
MANIFEST = json.loads((ROOT / "compatibility/manifest.json").read_text(encoding="utf-8"))

# Top-level directories and files that make up the running backend. An
# allowlist (not a denylist) so a new dev-only folder never leaks into the
# installer. The runtime import and smoke checks validate the staged output.
SOURCE_DIRS = (
    "agent", "api", "compatibility", "config", "connect", "core", "ears",
    "ecosystem", "founder_mode", "hands", "iqoo", "licensing", "memory",
    "mouth", "multimodal", "runtime", "skills", "sovereign",
)
SOURCE_FILES = ("sam_cli.py", "main.py", "requirements.txt", "LICENSE")
INTERFACES_DIRS = ("api", "telegram", "web")  # not "desktop": that is the GUI
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "tests", ".git", ".venv", "node_modules", "*.db",
    "chroma",
)

# Modules the core dependency group must be able to import after staging.
VERIFY_IMPORTS = ("requests", "yaml", "fastapi", "uvicorn", "httpx", "multipart", "cryptography")


def normalized_machine() -> str:
    machine = platform.machine().lower()
    return {"amd64": "x86_64", "aarch64": "arm64", "x64": "x86_64"}.get(machine, machine)


def system_key() -> str:
    return {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(platform.system(), "unsupported")


def run(args: list[str], **kwargs) -> None:
    print("+ " + " ".join(str(a) for a in args), flush=True)
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def copy_source(dest: Path) -> int:
    dest.mkdir(parents=True)
    count = 0
    for name in SOURCE_DIRS:
        origin = ROOT / name
        if not origin.is_dir():
            raise SystemExit(f"Required source directory is missing: {name}")
        shutil.copytree(origin, dest / name, ignore=IGNORE)
    (dest / "interfaces").mkdir()
    init = ROOT / "interfaces" / "__init__.py"
    if init.exists():
        shutil.copy2(init, dest / "interfaces" / "__init__.py")
    for name in INTERFACES_DIRS:
        origin = ROOT / "interfaces" / name
        if origin.is_dir():
            shutil.copytree(origin, dest / "interfaces" / name, ignore=IGNORE)
    for name in SOURCE_FILES:
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, dest / name)
    # Per-user data must never ship inside the installer.
    for leftover in ("memory/store", "founder_mode/store", "skills/compiled"):
        target = dest / leftover
        if target.exists():
            for child in target.iterdir():
                if child.name != ".gitkeep":
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
    for _ in dest.rglob("*"):
        count += 1
    return count


def dereference_symlinks(tree: Path) -> None:
    """Installer resource copiers do not reliably preserve symlinks. Replace
    each symlink that stays inside the tree with a real copy."""
    for path in sorted(tree.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not path.is_symlink():
            continue
        target = path.resolve()
        path.unlink()
        if target.is_dir():
            shutil.copytree(target, path, symlinks=False)
        elif target.exists():
            shutil.copy2(target, path)


def install_python(uv: str, version: str, work: Path, python_dir: Path) -> Path:
    install_dir = work / "uv-python"
    run([uv, "python", "install", "--install-dir", install_dir, version])
    if system_key() == "windows":
        executables = sorted(install_dir.rglob("python.exe"), key=lambda path: len(path.parts))
        if not executables:
            raise SystemExit("uv installed Python but no python.exe was produced.")
        # Prefer the managed CPython tree over uv's possible executable shim.
        # Copy it into the bundle so the runtime cannot retain references to
        # the temporary uv install directory, which is deleted after staging.
        cpython_roots = {
            parent for executable in executables for parent in executable.parents
            if parent.name.startswith("cpython-")
        }
        installation_root = sorted(cpython_roots, key=lambda path: len(path.parts), reverse=True)[0] \
            if cpython_roots else executables[0].parent
        shutil.copytree(installation_root, python_dir, symlinks=False)
    else:
        candidates = [p for p in install_dir.iterdir() if p.is_dir() and not p.is_symlink() and p.name.startswith("cpython-")]
        if not candidates:
            raise SystemExit("uv installed Python but no cpython-* directory was produced.")
        installation_root = sorted(candidates)[0]
        shutil.move(str(installation_root), str(python_dir))
    dereference_symlinks(python_dir)
    if system_key() == "windows":
        interpreter = python_dir / "python.exe"
    else:
        interpreter = python_dir / "bin" / "python3"
        if not interpreter.exists():
            versioned = sorted((python_dir / "bin").glob("python3.*"))
            if not versioned:
                raise SystemExit("Managed Python has no bin/python3 executable.")
            shutil.copy2(versioned[0], interpreter)
        interpreter.chmod(interpreter.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if not interpreter.exists():
        raise SystemExit(f"Managed Python executable not found at {interpreter}")
    return interpreter


def core_requirements() -> list[str]:
    out = subprocess.check_output(
        [sys.executable, str(ROOT / "runtime/environment_manager.py"),
         "resolve-dependencies", "--group", "core", "--format", "requirements"],
        cwd=ROOT, text=True,
    )
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if not lines:
        raise SystemExit("environment_manager resolved no core requirements.")
    return lines


def verify_runtime(interpreter: Path, source: Path, site_packages: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(source), str(site_packages)])
    env["PYTHONNOUSERSITE"] = "1"
    code = "import importlib,sys\n" + "".join(
        f"importlib.import_module({name!r})\n" for name in VERIFY_IMPORTS
    ) + "import config.settings, interfaces.api.server\nprint('runtime-import-ok', sys.version.split()[0])\n"
    result = subprocess.run([str(interpreter), "-c", code], cwd=source, env=env,
                            capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit("Staged runtime failed its import check; the installer must not be built from it.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--skip-deps", action="store_true", help="Stage source and Python only (tests).")
    parser.add_argument("--no-verify", action="store_true", help="Skip the import check (cross-built tests only).")
    args = parser.parse_args()

    key = system_key()
    if key == "unsupported":
        raise SystemExit(f"Unsupported operating system: {platform.system()}")
    arch = normalized_machine()
    if arch not in MANIFEST["platforms"][key]["architectures"]:
        raise SystemExit(f"{arch} is outside compatibility/manifest.json for {key}.")
    if key not in MANIFEST["distribution"]["consumer_platforms"]:
        raise SystemExit(f"{key} is not listed in distribution.consumer_platforms.")
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv is required on the packaging machine (https://docs.astral.sh/uv/).")
    version = MANIFEST["python"]["preferred_versions"][0]

    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sam-runtime-", dir=out.parent) as temp:
        work = Path(temp)
        stage = work / "sam-runtime"
        stage.mkdir()
        files = copy_source(stage / "source")
        interpreter = install_python(uv, version, work, stage / "python")
        site_packages = stage / "site-packages"
        site_packages.mkdir()
        if not args.skip_deps:
            run([uv, "pip", "install", "--python", interpreter, "--target", site_packages,
                 "pip>=24,<27"])
            run([uv, "pip", "install", "--python", interpreter, "--target", site_packages,
                 *core_requirements()])
        for cache in stage.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)
        if not args.skip_deps and not args.no_verify:
            relative_python = interpreter.relative_to(stage)
            verify_runtime(stage / relative_python, stage / "source", site_packages)
        relative_python = interpreter.relative_to(stage).as_posix()
        metadata = {
            "runtime_layout": 2,
            "os": key,
            "architecture": arch,
            "python_version": version,
            "python_executable": relative_python,
            "dependency_groups": [] if args.skip_deps else ["core"],
            "source_file_count": files,
            "created_unix": int(time.time()),
            "optional_capability_strategy": "user-writable-python-packages",
            "optional_dependency_groups": [],
            "user_data_root": "~/.sam_data",
            "user_packages_dir": "~/.sam_data/python-packages",
        }
        (stage / "bundle.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        backup = None
        if (out / "README.md").exists():  # tracked in git; keep it across restages
            shutil.copy2(out / "README.md", stage / "README.md")
        if out.exists():
            backup = out.with_name("sam-runtime.previous-{}".format(time.strftime("%Y%m%d%H%M%S")))
            out.rename(backup)
        try:
            stage.rename(out)
        except Exception:
            if backup and backup.exists() and not out.exists():
                backup.rename(out)
            raise
        bundled_interpreter = out / relative_python
        if not bundled_interpreter.is_file():
            if backup is not None and backup.exists():
                failed_stage = out.with_name(out.name + ".incomplete")
                out.rename(failed_stage)
                backup.rename(out)
            raise SystemExit("Staged runtime lost its Python executable after relocation: {}".format(
                bundled_interpreter))
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
    print(f"Staged {key}/{arch} runtime at {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
