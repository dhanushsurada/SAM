"""Reusable environment discovery, capability, and recovery services.

The installers call this manager for preflight checks. Runtime features can
also use its report to explain which local capabilities are ready without
starting or changing those services.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

try:  # direct script execution and package import are both supported
    from .compatibility import (
        CompatibilityError, check_platform, check_requirements, check_tools,
        load_manifest, resolve_python,
    )
except ImportError:  # pragma: no cover - exercised by setup.sh subprocess
    from compatibility import (
        CompatibilityError, check_platform, check_requirements, check_tools,
        load_manifest, resolve_python,
    )


class EnvironmentCompatibilityManager:
    """Discover SAM's local environment and produce actionable diagnostics."""

    def __init__(self, manifest: Optional[dict] = None, root: Optional[Path] = None,
                 which: Callable[[str], Optional[str]] = shutil.which,
                 runner: Callable = subprocess.run,
                 opener: Callable = urllib.request.urlopen):
        self.manifest = manifest or load_manifest()
        self.root = Path(root) if root else Path(__file__).resolve().parents[1]
        self.which = which
        self.runner = runner
        self.opener = opener

    def discover(self) -> dict:
        """Return a read-only snapshot of OS, hardware, tools, and packages."""
        versions = {}
        python_policy = self.manifest["python"]
        executable_candidates = list(dict.fromkeys(
            list(python_policy["executables"].values()) + python_policy["bootstrap_candidates"]
        ))
        for name in executable_candidates:
            path = self.which(name)
            if path:
                try:
                    result = self.runner([path, "--version"], capture_output=True,
                                         text=True, timeout=5, check=False)
                    value = (result.stdout or result.stderr).strip()
                    if result.returncode == 0:
                        versions[name] = {"path": path, "version": value}
                except (OSError, subprocess.SubprocessError):
                    pass

        tools = {}
        for name, policy in self.manifest.get("tools", {}).items():
            executable = {"rust": "rustc"}.get(name, name)
            path = self.which(executable)
            entry = {"installed": bool(path), "path": path, "minimum_version": policy.get("minimum_version")}
            if path:
                try:
                    result = self.runner([path, "--version"], capture_output=True,
                                         text=True, timeout=5, check=False)
                    if result.returncode == 0:
                        entry["version"] = (result.stdout or result.stderr).strip()
                except (OSError, subprocess.SubprocessError):
                    pass
            tools[name] = entry

        package_groups = {}
        import_names = python_policy.get("import_names", {})
        for group, requirements in python_policy.get("dependency_groups", {}).items():
            package_groups[group] = {
                package: self._module_available(import_names.get(package, package.replace("-", "_")))
                for package in requirements
            }
        return {
            "sam": {"version_policy": self.manifest.get("sam", {}).get("version_policy", "unspecified")},
            "os": {"name": platform.system(), "version": platform.mac_ver()[0] or platform.release(),
                   "release": platform.release(), "architecture": platform.machine()},
            "python": {"current": platform.python_version(), "executable": sys.executable,
                       "available": versions, "supported": python_policy["supported_versions"]},
            "hardware": {"memory_gb": self._memory_gb(), "cpu_count": os.cpu_count()},
            "tools": tools,
            "dependencies": package_groups,
        }

    @staticmethod
    def _module_available(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError, ModuleNotFoundError):
            return False

    @staticmethod
    def _memory_gb() -> Optional[int]:
        try:
            if sys.platform == "darwin":
                result = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                                        text=True, timeout=3, check=True)
                return int(result.stdout.strip()) // (1024 ** 3)
            if sys.platform.startswith("linux"):
                for line in Path("/proc/meminfo").read_text().splitlines():
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) // (1024 ** 2)
            if sys.platform == "win32":
                import ctypes
                class MemoryStatus(ctypes.Structure):
                    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                                ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
                                ("page_total", ctypes.c_ulonglong), ("page_available", ctypes.c_ulonglong),
                                ("virtual_total", ctypes.c_ulonglong), ("virtual_available", ctypes.c_ulonglong),
                                ("extended", ctypes.c_ulonglong)]
                status = MemoryStatus()
                status.length = ctypes.sizeof(status)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                    return int(status.total) // (1024 ** 3)
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
        return None

    def capabilities(self, settings: Optional[dict] = None) -> dict:
        """Probe optional runtimes without starting them or downloading models."""
        settings = settings or {}
        endpoint = self.manifest.get("capabilities", {}).get("ollama", {}).get(
            "endpoint", "http://127.0.0.1:11434/api/tags")
        host = str(settings.get("ollama_host", endpoint.rsplit("/api/tags", 1)[0])).rstrip("/")
        ollama = {"available": False, "models": [], "configured_models": {}, "detail": "not responding"}
        try:
            request = urllib.request.Request(host + "/api/tags", headers={"Accept": "application/json"})
            with self.opener(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            names = [item.get("name") or item.get("model") for item in payload.get("models", [])
                     if isinstance(item, dict)]
            ollama.update(available=True, models=names, detail="Ollama API is ready")
            for key in ("primary_model", "fallback_model", "embedding_model", "vision_model"):
                model = settings.get(key)
                if model:
                    ollama["configured_models"][key] = {"name": model, "available": model in names}
        except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
            ollama["detail"] = "Ollama is unavailable: {}".format(exc)

        audio_modules = self.manifest.get("capabilities", {}).get("audio_capture", {}).get("python_modules", [])
        browser_modules = self.manifest.get("capabilities", {}).get("browser_automation", {}).get("python_modules", [])
        return {
            "ollama": ollama,
            "audio_capture": {"available": any(self._module_available(item) for item in audio_modules),
                              "modules": {item: self._module_available(item) for item in audio_modules}},
            "browser_automation": {"available": all(self._module_available(item) for item in browser_modules),
                                  "modules": {item: self._module_available(item) for item in browser_modules}},
        }

    def dependency_plan(self, groups: Optional[list[str]] = None) -> dict:
        """Resolve manifest groups to currently declared requirements lines."""
        policy = self.manifest["python"]
        definitions = policy["dependency_groups"]
        selected = groups or list(definitions)
        unknown = sorted(set(selected) - set(definitions))
        if unknown:
            raise CompatibilityError("Unknown dependency group(s): {}. Available: {}".format(
                ", ".join(unknown), ", ".join(definitions)))
        requirements_path = self.root / policy["requirements_file"]
        lines = []
        for raw in requirements_path.read_text(encoding="utf-8").splitlines():
            stripped = raw.split("#", 1)[0].strip()
            if not stripped or stripped.startswith(("-", ".")):
                continue
            import re
            match = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?", stripped)
            if match and any(match.group(1).lower().replace("_", "-") == name.lower().replace("_", "-")
                             for group in selected for name in definitions[group]):
                lines.append(stripped)
        return {"groups": selected, "requirements_file": str(requirements_path),
                "requirements": lines, "required_for_install": policy.get("required_groups", [])}

    def dependency_status(self) -> dict:
        """Separate install-critical packages from optional capabilities."""
        report = self.discover()["dependencies"]
        required = set(self.manifest["python"].get("required_groups", []))
        status = {}
        for group, packages in report.items():
            missing = [name for name, available in packages.items() if not available]
            status[group] = {"required": group in required, "available": not missing,
                             "missing": missing,
                             "recovery": ("Install the SAM requirements for this group from requirements.txt."
                                          if missing else "ready")}
        return status

    def diagnostics(self, os_name: Optional[str] = None, os_version: Optional[str] = None,
                    architecture: Optional[str] = None) -> list[dict]:
        """Report policy gaps with a concrete recovery instruction per gap."""
        issues = []
        try:
            check_platform(self.manifest, os_name, os_version, architecture)
        except CompatibilityError as exc:
            issues.append({"severity": "error", "area": "platform", "message": str(exc)})
        try:
            executable, version = resolve_python(self.manifest)
            issues.append({"severity": "ok", "area": "python", "message": "Using Python {} at {}".format(version, executable)})
        except CompatibilityError as exc:
            issues.append({"severity": "error", "area": "python", "message": str(exc)})
        try:
            check_tools(self.manifest, which=self.which, runner=self.runner)
        except CompatibilityError as exc:
            issues.append({"severity": "error", "area": "tools", "message": str(exc)})
        try:
            check_requirements(self.manifest, self.root / self.manifest["python"]["requirements_file"])
        except (CompatibilityError, OSError) as exc:
            issues.append({"severity": "error", "area": "dependencies", "message": str(exc)})
        for group, state in self.dependency_status().items():
            if state["missing"]:
                severity = "error" if state["required"] else "info"
                issues.append({"severity": severity, "area": "dependency:" + group,
                               "message": "Missing {} package(s): {}. {}".format(
                                   group, ", ".join(state["missing"]), state["recovery"] )})
        memory = self._memory_gb()
        minimum = self.manifest.get("sam", {}).get("minimum_memory_gb")
        if memory is not None and minimum and memory < minimum:
            issues.append({"severity": "warning", "area": "hardware",
                           "message": "Detected {} GB RAM; SAM recommends {} GB or more. Choose a smaller local model in Settings.".format(memory, minimum)})
        return issues

    @staticmethod
    def record_setup_step(step: str, state: str, detail: str = "",
                          path: Optional[Path] = None) -> dict:
        """Persist progress atomically, preserving earlier setup steps."""
        if state not in {"started", "complete", "blocked"}:
            raise ValueError("setup step state must be started, complete, or blocked")
        if not step or any(ch.isspace() for ch in step):
            raise ValueError("setup step name must be a non-empty token")
        target = path or (Path.home() / ".sam_data" / "environment_setup.json")
        try:
            data = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {"schema_version": 1, "steps": {}}
        except (OSError, json.JSONDecodeError):
            raise CompatibilityError("Setup recovery state is unreadable; preserve it and inspect {} before retrying".format(target))
        data.setdefault("schema_version", 1)
        data.setdefault("steps", {})[step] = {"state": state, "detail": detail}
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(str(temporary), str(target))
        return data


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="SAM environment and compatibility manager")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("discover")
    commands.add_parser("capabilities")
    commands.add_parser("diagnose")
    commands.add_parser("preflight")
    dependencies = commands.add_parser("resolve-dependencies")
    dependencies.add_argument("--group", action="append", dest="groups")
    step = commands.add_parser("record-step")
    step.add_argument("name")
    step.add_argument("state", choices=("started", "complete", "blocked"))
    step.add_argument("--detail", default="")
    args = parser.parse_args(argv)
    manager = EnvironmentCompatibilityManager()
    if args.command == "discover":
        output = manager.discover()
    elif args.command == "capabilities":
        output = manager.capabilities()
    elif args.command == "resolve-dependencies":
        output = manager.dependency_plan(args.groups)
    elif args.command in {"diagnose", "preflight"}:
        output = manager.diagnostics()
        failed = any(issue["severity"] == "error" for issue in output)
        if args.command == "preflight":
            failed = any(issue["severity"] == "error" and not issue["area"].startswith("dependency:")
                         for issue in output)
        if args.command == "preflight" and failed:
            print(json.dumps(output, indent=2))
            return 1
    else:
        output = manager.record_setup_step(args.name, args.state, args.detail)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
