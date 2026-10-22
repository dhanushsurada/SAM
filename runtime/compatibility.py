"""Compatibility policy and prerequisite checks used by source installers.

This module intentionally stays compatible with Apple's Python 3.9 bootstrap
interpreter; the SAM runtime itself is restricted by the manifest to Python
3.11 and 3.12.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "compatibility" / "manifest.json"
VERSION_RE = re.compile(r"(?:Python\s+|v)?(\d+)\.(\d+)(?:\.(\d+))?")
REQUIREMENT_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^]]+\])?\s*(?:[<>=!~].*)?$")


class CompatibilityError(RuntimeError):
    pass


def load_manifest(path: Optional[Path] = None) -> dict:
    manifest_path = path or DEFAULT_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompatibilityError("Cannot read SAM compatibility manifest at {}: {}".format(manifest_path, exc))
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict) -> None:
    if manifest.get("schema_version") != 1:
        raise CompatibilityError("Unsupported compatibility manifest schema_version")
    python = manifest.get("python", {})
    supported = python.get("supported_versions", [])
    preferred = python.get("preferred_versions", [])
    if not supported or not preferred or any(version not in supported for version in preferred):
        raise CompatibilityError("Python preferred_versions must be selected from supported_versions")
    if not python.get("bootstrap_formula"):
        raise CompatibilityError("Python bootstrap_formula is missing")
    if not python.get("bootstrap_executable") or any(v not in python.get("executables", {}) for v in supported):
        raise CompatibilityError("Python executable map is incomplete")
    if not python.get("dependency_groups") or not python.get("requirements_file"):
        raise CompatibilityError("Python dependency groups or requirements_file are missing")
    for tool in ("node", "npm", "rust"):
        if not manifest.get("tools", {}).get(tool, {}).get("minimum_version"):
            raise CompatibilityError("Minimum version for required tool {!r} is missing".format(tool))


def _platform_key(name: Optional[str] = None) -> str:
    value = (name or platform.system()).lower()
    return {"darwin": "macos", "macos": "macos"}.get(value, value)


def _architecture(value: Optional[str] = None) -> str:
    arch = (value or platform.machine()).lower()
    return {"aarch64": "arm64", "amd64": "x86_64"}.get(arch, arch)


def check_platform(manifest: dict, os_name: Optional[str] = None,
                   os_version: Optional[str] = None,
                   architecture: Optional[str] = None) -> None:
    key = _platform_key(os_name)
    policy = manifest.get("platforms", {}).get(key)
    if not policy:
        raise CompatibilityError("SAM has no installer compatibility policy for {}".format(key))
    arch = _architecture(architecture)
    if arch not in policy.get("architectures", []):
        raise CompatibilityError(
            "Unsupported {} architecture: {}. Supported: {}".format(
                key, arch, ", ".join(policy.get("architectures", []))
            )
        )
    minimum = policy.get("minimum_version")
    current_version = os_version or platform.mac_ver()[0]
    if minimum and _version_tuple(current_version) < _version_tuple(minimum):
        raise CompatibilityError(
            "SAM's macOS installer requires macOS {} or later for its Ollama app dependency; "
            "this machine is running {}. Install a supported macOS version or use the documented manual setup.".format(
                minimum, current_version or "an unknown version"
            )
        )


def _version_tuple(value: str) -> Tuple[int, ...]:
    match = VERSION_RE.search(str(value))
    if not match:
        raise CompatibilityError("Could not parse version string {!r}".format(value))
    return tuple(int(part or 0) for part in match.groups())


def _reported_version(executable: str,
                       runner: Callable = subprocess.run) -> Optional[str]:
    try:
        result = runner([executable, "--version"], capture_output=True,
                        text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    output = (result.stdout or "") + " " + (result.stderr or "")
    match = VERSION_RE.search(output)
    if result.returncode != 0 or not match:
        return None
    return "{}.{}.{}".format(match.group(1), match.group(2), match.group(3) or "0")


def _python_version(executable: str,
                    runner: Callable = subprocess.run) -> Optional[str]:
    reported = _reported_version(executable, runner)
    if reported is None:
        return None
    major, minor, _patch = reported.split(".")
    return "{}.{}".format(major, minor)


def resolve_python(manifest: Optional[dict] = None,
                   candidates: Optional[Sequence[str]] = None,
                   which: Callable[[str], Optional[str]] = shutil.which,
                   runner: Callable = subprocess.run) -> Tuple[str, str]:
    policy = (manifest or load_manifest())["python"]
    supported = policy["supported_versions"]
    preferred = policy["preferred_versions"]
    default_names = [policy["executables"][version] for version in preferred] + ["python3"]
    names = list(candidates or default_names)
    found: Dict[str, str] = {}
    for name in names:
        executable = which(name)
        if executable:
            version = _python_version(executable, runner)
            if version:
                found.setdefault(version, executable)
    for version in preferred:
        if version in supported and version in found:
            return found[version], version
    detected = ", ".join("{} ({})".format(name, version) for version, name in found.items()) or "none"
    formulas = (manifest or load_manifest()).get("platforms", {}).get("macos", {}).get("python_formulas", {})
    formula_list = ", ".join(formulas.get(version, "python@" + version) for version in preferred)
    raise CompatibilityError(
        "No supported Python interpreter was found. Detected: {}. SAM supports Python {}. "
        "Install a supported version with Homebrew (for example: brew install {}).".format(
            detected, " or ".join(supported), formula_list
        )
    )


def check_python(executable: str, manifest: Optional[dict] = None,
                 runner: Callable = subprocess.run) -> str:
    policy = (manifest or load_manifest())["python"]
    version = _python_version(executable, runner)
    if version not in policy["supported_versions"]:
        raise CompatibilityError(
            "{} reports Python {}; SAM supports Python {}. Preserve this environment and create a new one "
            "with a supported interpreter.".format(
                executable, version or "unknown", " or ".join(policy["supported_versions"])
            )
        )
    return version


def check_tools(manifest: Optional[dict] = None,
                names: Iterable[str] = ("node", "npm", "rust"),
                which: Callable[[str], Optional[str]] = shutil.which,
                runner: Callable = subprocess.run) -> None:
    data = manifest or load_manifest()
    executable_names = {"node": "node", "npm": "npm", "rust": "rustc"}
    for name in names:
        policy = data.get("tools", {}).get(name)
        if not policy:
            raise CompatibilityError("No compatibility policy is defined for tool {!r}".format(name))
        executable = which(executable_names[name])
        if not executable:
            formula = policy.get("homebrew_formula")
            raise CompatibilityError("Required tool {} is missing; install it with Homebrew{}".format(
                name, " (brew install {})".format(formula) if formula else ""
            ))
        version = _reported_version(executable, runner)
        if not version:
            # npm and cargo/rustc may prefix versions with a tool name. The
            # same version parser handles those outputs.
            raise CompatibilityError("Could not read {} version from {}".format(name, executable))
        actual = _version_tuple(version)
        minimum = _version_tuple(policy["minimum_version"])
        if actual < minimum:
            formula = policy.get("homebrew_formula")
            raise CompatibilityError(
                "{} {} is below SAM's supported minimum {}. Update it{} and retry.".format(
                    name, version, policy["minimum_version"],
                    " with brew upgrade {}".format(formula) if formula else ""
                )
            )


def check_requirements(manifest: Optional[dict] = None,
                       requirements_path: Optional[Path] = None) -> None:
    data = manifest or load_manifest()
    path = requirements_path or (ROOT / data["python"]["requirements_file"])
    declared = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped or stripped.startswith(("-", ".")):
            continue
        match = REQUIREMENT_RE.match(stripped)
        if match:
            declared.add(match.group(1).lower().replace("_", "-"))
    missing = []
    for group in data["python"]["dependency_groups"].values():
        missing.extend(name for name in group if name.lower().replace("_", "-") not in declared)
    if missing:
        raise CompatibilityError(
            "Compatibility manifest dependencies are absent from {}: {}".format(path, ", ".join(sorted(set(missing))))
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SAM installer compatibility checks")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("select-python", help="print the preferred supported Python executable")
    check_parser = subparsers.add_parser("check-python", help="validate an existing interpreter")
    check_parser.add_argument("executable")
    platform_parser = subparsers.add_parser("check-platform", help="validate macOS version and architecture")
    platform_parser.add_argument("--os", default="macos")
    platform_parser.add_argument("--version", default=None)
    platform_parser.add_argument("--architecture", default=None)
    tools_parser = subparsers.add_parser("check-tools", help="check installed desktop tool versions")
    tools_parser.add_argument("tools", nargs="*", default=["node", "npm", "rust"])
    subparsers.add_parser("check-requirements", help="check manifest dependencies against requirements.txt")
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest()
        if args.command == "select-python":
            executable, version = resolve_python(manifest)
            print(executable)
            print("SAM will use supported Python {}.".format(version), file=sys.stderr)
        elif args.command == "check-python":
            print(check_python(args.executable, manifest))
        elif args.command == "check-platform":
            check_platform(manifest, args.os, args.version, args.architecture)
        elif args.command == "check-tools":
            check_tools(manifest, args.tools)
        elif args.command == "check-requirements":
            check_requirements(manifest)
    except CompatibilityError as exc:
        print("SAM compatibility check failed: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
