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
        parse_requirements, satisfies_specifier,
        load_manifest, resolve_python,
    )
except ImportError:  # pragma: no cover - exercised by setup.sh subprocess
    from compatibility import (
        CompatibilityError, check_platform, check_requirements, check_tools,
        parse_requirements, satisfies_specifier,
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
        selected = list(groups) if groups is not None else list(policy.get("default_groups", policy.get("required_groups", [])))
        unknown = sorted(set(selected) - set(definitions))
        if unknown:
            raise CompatibilityError("Unknown dependency group(s): {}. Available: {}".format(
                ", ".join(unknown), ", ".join(definitions)))
        requirements_path = self.root / policy["requirements_file"]
        all_requirements = parse_requirements(requirements_path)
        selected_names = {name.lower().replace("_", "-") for group in selected for name in definitions[group]}
        lines = [declaration["requirement"] for name, declaration in all_requirements.items()
                 if name in selected_names]
        return {"groups": selected, "requirements_file": str(requirements_path),
                "requirements": lines, "required_for_install": policy.get("required_groups", [])}

    def dependency_status(self) -> dict:
        """Separate install-critical packages from optional capabilities."""
        report = self.discover()["dependencies"]
        required = set(self.manifest["python"].get("required_groups", []))
        requirement_specs = parse_requirements(self.root / self.manifest["python"]["requirements_file"])
        import importlib.metadata
        status = {}
        for group, packages in report.items():
            missing, incompatible = [], []
            versions = {}
            for name, available in packages.items():
                normalized = name.lower().replace("_", "-")
                try:
                    version = importlib.metadata.version(normalized)
                    versions[name] = version
                except importlib.metadata.PackageNotFoundError:
                    version = None
                if not available or version is None:
                    missing.append(name)
                elif not satisfies_specifier(version, requirement_specs.get(normalized, {}).get("specifier", "")):
                    incompatible.append({"name": name, "installed": version,
                                         "required": requirement_specs.get(normalized, {}).get("specifier", "")})
            recovery = ("Install the SAM requirements for this group from requirements.txt."
                        if missing else ("Upgrade packages to satisfy requirements.txt."
                                         if incompatible else "ready"))
            status[group] = {"required": group in required, "available": not missing and not incompatible,
                             "missing": missing, "incompatible": incompatible, "versions": versions,
                             "recovery": recovery}
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
            if state["missing"] or state["incompatible"]:
                severity = "error" if state["required"] else "info"
                issues.append({"severity": severity, "area": "dependency:" + group,
                               "message": "Dependency group {} has missing packages {} and incompatible versions {}. {}".format(
                                   group, state["missing"], state["incompatible"], state["recovery"] )})
        for group, state in self.system_dependency_status().items():
            if state["missing"] or state.get("missing_libraries") or state.get("missing_tools"):
                missing_items = (state["missing"] + state.get("missing_libraries", [])
                                 + state.get("missing_tools", []))
                issues.append({"severity": "info", "area": "system_dependency:" + group,
                               "message": "{} Missing: {}. {}".format(
                                   state["message"], ", ".join(missing_items),
                                   state.get("install_hint", "")).strip()})
        memory = self._memory_gb()
        minimum = self.manifest.get("sam", {}).get("minimum_memory_gb")
        if memory is not None and minimum and memory < minimum:
            issues.append({"severity": "warning", "area": "hardware",
                           "message": "Detected {} GB RAM; SAM recommends {} GB or more. Choose a smaller local model in Settings.".format(memory, minimum)})
        return issues

    def system_dependency_status(self) -> dict:
        """Describe optional OS prerequisites without making them core blockers."""
        os_key = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system(), "")
        groups = {}
        for group, policies in self.manifest.get("system_dependencies", {}).items():
            policy = policies.get(os_key, {})
            manager = policy.get("manager")
            packages = policy.get("packages", [])
            missing = []
            if manager == "brew":
                brew = self.which("brew")
                for package in packages:
                    try:
                        result = self.runner([brew or "brew", "list", package], capture_output=True,
                                             text=True, timeout=5, check=False)
                        if result.returncode != 0:
                            missing.append(package)
                    except (OSError, subprocess.SubprocessError):
                        missing.append(package)
            elif manager == "apt":
                for package in packages:
                    try:
                        result = self.runner(["dpkg-query", "-W", "-f=${Status}", package],
                                             capture_output=True, text=True, timeout=5, check=False)
                        if result.returncode != 0 or "install ok installed" not in result.stdout:
                            missing.append(package)
                    except (OSError, subprocess.SubprocessError):
                        missing.append(package)
            missing_libraries = []
            libraries = policy.get("libraries", [])
            if libraries and platform.system() == "Linux":
                try:
                    result = self.runner(["ldconfig", "-p"], capture_output=True, text=True,
                                         timeout=8, check=False)
                    available_libraries = result.stdout or ""
                    missing_libraries = [library for library in libraries
                                         if library not in available_libraries]
                except (OSError, subprocess.SubprocessError):
                    missing_libraries = list(libraries)
            missing_tools = [tool for tool in policy.get("tools", []) if not self.which(tool)]
            groups[group] = {"manager": manager, "missing": missing,
                             "missing_libraries": missing_libraries,
                             "missing_tools": missing_tools,
                             "message": policy.get("reason", ""),
                             "install_hint": (("brew install " if manager == "brew" else "sudo apt-get install ")
                                              + " ".join(missing)
                                              if missing and manager in {"brew", "apt"} else "")}
        return groups

    def system_dependency_plan(self, group: str) -> dict:
        os_key = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system(), "")
        definition = self.manifest.get("system_dependencies", {}).get(group)
        if definition is None:
            raise CompatibilityError("Unknown system dependency group {!r}".format(group))
        policy = definition.get(os_key, {})
        return {"group": group, "platform": os_key, "manager": policy.get("manager"),
                "packages": policy.get("packages", []), "tools": policy.get("tools", []),
                "reason": policy.get("reason", "")}

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
    dependencies.add_argument("--format", choices=("json", "requirements"), default="json")
    system_dependencies = commands.add_parser("system-dependencies")
    system_dependencies.add_argument("--group", required=True)
    system_dependencies.add_argument("--format", choices=("json", "packages", "missing"), default="json")
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
    elif args.command == "system-dependencies":
        output = (manager.system_dependency_status().get(args.group, {})
                  if args.format == "missing" else manager.system_dependency_plan(args.group))
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
    if args.command == "resolve-dependencies" and args.format == "requirements":
        print("\n".join(output["requirements"]))
    elif args.command == "system-dependencies" and args.format == "packages":
        print("\n".join(output["packages"]))
    elif args.command == "system-dependencies" and args.format == "missing":
        print("\n".join(output.get("missing", []) + output.get("missing_libraries", []) + output.get("missing_tools", [])))
    else:
        print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
