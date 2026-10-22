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
import datetime
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

try:  # direct script execution and package import are both supported
    from .compatibility import (
        CompatibilityError, check_platform, check_requirements, check_tools,
        parse_requirements, satisfies_specifier, check_python,
        load_manifest, resolve_python, available_python_interpreters,
    )
except ImportError:  # pragma: no cover - exercised by setup.sh subprocess
    from compatibility import (
        CompatibilityError, check_platform, check_requirements, check_tools,
        parse_requirements, satisfies_specifier, check_python,
        load_manifest, resolve_python, available_python_interpreters,
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
        self._discovery_cache = None

    def discover(self) -> dict:
        """Return a read-only snapshot of OS, hardware, tools, and packages."""
        if self._discovery_cache is not None:
            return self._discovery_cache
        versions = {}
        python_policy = self.manifest["python"]
        for version, path in available_python_interpreters(self.manifest, self.which, self.runner).items():
            versions[version] = {"path": path, "version": version}
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
            executable = {"rust": "rustc", "homebrew": "brew",
                          "xcode_command_line_tools": "xcode-select"}.get(name, name)
            path = self.which(executable)
            entry = {"installed": bool(path), "path": path, "minimum_version": policy.get("minimum_version")}
            if path and name != "xcode_command_line_tools":
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
        try:
            selected_python = {"path": resolve_python(self.manifest, which=self.which,
                                                       runner=self.runner)[0], "supported": True}
        except CompatibilityError as exc:
            selected_python = {"path": None, "supported": False, "detail": str(exc)}
        try:
            disk = shutil.disk_usage(self.root)
            disk_info = {"total_gb": round(disk.total / (1024 ** 3), 2),
                         "free_gb": round(disk.free / (1024 ** 3), 2)}
        except OSError as exc:
            disk_info = {"total_gb": None, "free_gb": None, "detail": str(exc)}
        os_version = platform.mac_ver()[0] if platform.system() == "Darwin" else platform.release()
        if platform.system() == "Linux" and hasattr(platform, "freedesktop_os_release"):
            try:
                release = platform.freedesktop_os_release()
                os_version = "{} {}".format(release.get("ID", "Linux"), release.get("VERSION_ID", platform.release()))
            except (OSError, AttributeError):
                pass
        self._discovery_cache = {
            "sam": {"version_policy": self.manifest.get("sam", {}).get("version_policy", "unspecified")},
            "os": {"name": platform.system(), "version": os_version,
                   "release": platform.release(), "architecture": platform.machine()},
            "python": {"current": platform.python_version(), "executable": sys.executable,
                       "available": versions, "supported": python_policy["supported_versions"],
                       "selected": selected_python},
            "hardware": {"memory_gb": self._memory_gb(), "cpu_count": os.cpu_count(),
                         "disk": disk_info},
            "tools": tools,
            "dependencies": package_groups,
        }
        return self._discovery_cache

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
            # Endpoint URLs may contain credentials. Diagnostics expose a
            # safe state, never the exception string or configured URL.
            ollama["detail"] = "Ollama is unavailable at the configured endpoint."

        audio_modules = self.manifest.get("capabilities", {}).get("audio_capture", {}).get("python_modules", [])
        browser_modules = self.manifest.get("capabilities", {}).get("browser_automation", {}).get("python_modules", [])
        dependency_status = self.dependency_status()
        system_status = self.system_dependency_status()
        feature_groups = {}
        for group in ("voice", "vision", "memory", "integrations"):
            package_state = dependency_status.get(group, {"available": True, "missing": [], "incompatible": []})
            system_state = system_status.get(group, {"missing": [], "missing_libraries": [], "missing_tools": []})
            missing_os = system_state.get("missing", []) + system_state.get("missing_libraries", []) + system_state.get("missing_tools", [])
            feature_groups[group] = {
                "available": package_state["available"] and not missing_os,
                "missing_packages": package_state.get("missing", []),
                "incompatible_packages": package_state.get("incompatible", []),
                "missing_system_prerequisites": missing_os,
                "reason": ("Install the optional '{}' dependency group and its listed prerequisites.".format(group)
                           if package_state.get("missing") or package_state.get("incompatible") or missing_os else "ready"),
            }
        ollama_installed = bool(self.which("ollama"))
        configured_model = settings.get("primary_model")
        configured_available = bool(configured_model and configured_model in ollama["models"])
        ollama.update(installed=ollama_installed,
                      configured_model=configured_model,
                      configured_model_available=configured_available,
                      state="READY" if ollama["available"] and configured_available else ("DEGRADED" if ollama["available"] else "STOPPED"))
        return {
            "ollama": ollama,
            "audio_capture": {"available": any(self._module_available(item) for item in audio_modules),
                              "modules": {item: self._module_available(item) for item in audio_modules}},
            "browser_automation": {"available": all(self._module_available(item) for item in browser_modules),
                                  "modules": {item: self._module_available(item) for item in browser_modules}},
            "features": feature_groups,
        }

    def report(self, settings: Optional[dict] = None) -> dict:
        """Produce a credential-safe status payload for local UI diagnostics."""
        from runtime.setup_state import read_setup_state

        journal_path = Path.home() / ".sam_data" / "environment_setup.json"
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8")) if journal_path.exists() else {"steps": {}}
        except (OSError, json.JSONDecodeError):
            journal = {"steps": {}, "state": "unreadable"}
        return {
            "environment": self.discover(),
            "diagnostics": self.diagnostics(),
            "dependencies": self.dependency_status(),
            "capabilities": self.capabilities(settings),
            "setup": {"journey": read_setup_state(), "installation": journal,
                      "dependency_repair_supported": Path(sys.prefix).resolve() == (self.root / ".venv").resolve()},
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

    def repair_dependencies(self, groups: list[str]) -> dict:
        """Repair selected dependency groups in the active SAM environment.

        This is an explicit user action from Diagnostics. Pip receives the
        manifest's pinned requirement specifiers, never package names from
        the request. A failed repair is journaled and leaves user data intact.
        """
        source_venv = (self.root / ".venv").resolve()
        if Path(sys.prefix).resolve() != source_venv:
            raise CompatibilityError("In-app dependency repair is available for source installs only. "
                                     "This managed runtime is read-only; install a refreshed SAM package "
                                     "or use the supported source setup route.")
        plan = self.dependency_plan(groups)
        if not plan["requirements"]:
            raise CompatibilityError("The selected dependency groups contain no declared requirements")
        self.record_setup_step("dependency-repair", "started",
                               "Installing groups: " + ", ".join(plan["groups"]))
        try:
            result = self.runner([sys.executable, "-m", "pip", "install", *plan["requirements"]],
                                 capture_output=True, text=True, timeout=1800, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            self.record_setup_step("dependency-repair", "blocked", str(exc))
            raise CompatibilityError("Dependency repair could not start: {}".format(exc)) from exc
        if result.returncode:
            detail = (result.stderr or result.stdout or "pip failed without details").strip()[-4000:]
            self.record_setup_step("dependency-repair", "blocked", detail)
            raise CompatibilityError("Dependency repair failed. Existing settings and models were preserved. "
                                     "Resolve the package or network issue and retry. {}".format(detail))
        self._discovery_cache = None
        self.record_setup_step("dependency-repair", "complete",
                               "Repaired groups: " + ", ".join(plan["groups"]))
        return {"state": "complete", "groups": plan["groups"], "report": self.report()}

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
            has_desktop_sources = (self.root / "interfaces" / "desktop" / "src-tauri").is_dir()
            tool_names = (("node", "npm", "rust")
                          if has_desktop_sources and platform.system() in {"Darwin", "Windows"} else ())
            if tool_names:
                check_tools(self.manifest, names=tool_names, which=self.which, runner=self.runner)
            if has_desktop_sources and platform.system() == "Darwin":
                for executable, label, args in (
                    ("brew", "Homebrew", ["--version"]),
                    ("xcode-select", "Apple Command Line Tools", ["-p"]),
                ):
                    path = self.which(executable)
                    if not path:
                        issues.append({"severity": "error", "area": "tools",
                                       "message": "{} is missing; install it before building the macOS desktop app.".format(label)})
                    elif executable == "xcode-select":
                        try:
                            result = self.runner([path, *args], capture_output=True, text=True, timeout=5, check=False)
                            if result.returncode:
                                issues.append({"severity": "error", "area": "tools",
                                               "message": "Apple Command Line Tools are not configured. Run xcode-select --install and complete the prompt."})
                        except (OSError, subprocess.SubprocessError):
                            issues.append({"severity": "error", "area": "tools",
                                           "message": "Could not query Apple Command Line Tools; run xcode-select --install."})
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
        previous = data.setdefault("steps", {}).get(step, {})
        attempts = int(previous.get("attempts", 0)) + (1 if state == "started" else 0)
        data["steps"][step] = {"state": state, "detail": detail,
                               "attempts": attempts or int(previous.get("attempts", 0)),
                               "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(str(temporary), str(target))
        if step == "python-dependencies" and state == "complete":
            # Dependency installation has committed successfully; the prior
            # environment is no longer the rollback target for later runs.
            (Path(__file__).resolve().parents[1] / ".venv.recovery.json").unlink(missing_ok=True)
        return data

    def prepare_virtualenv(self, python: str, target: Path) -> dict:
        """Create a compatible venv, preserving any unusable prior environment."""
        target = Path(target).expanduser().resolve()
        version = check_python(python, self.manifest, self.runner)
        executable = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        reusable = False
        if executable.is_file():
            try:
                check_python(str(executable), self.manifest, self.runner)
                reusable = True
            except CompatibilityError:
                reusable = False
        if reusable:
            return {"path": str(target), "python": str(executable), "created": False,
                    "detail": "Existing supported virtual environment preserved."}
        backup = None
        if target.exists():
            stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            backup = target.with_name(target.name + ".backup-" + stamp)
            suffix = 1
            while backup.exists():
                backup = target.with_name(target.name + ".backup-{}-{}".format(stamp, suffix))
                suffix += 1
            target.rename(backup)
            marker = target.with_name(target.name + ".recovery.json")
            if not marker.exists():
                marker_tmp = marker.with_name(marker.name + ".tmp")
                marker_tmp.write_text(json.dumps({"target": str(target), "backup": str(backup)}, indent=2) + "\n",
                                      encoding="utf-8")
                os.replace(str(marker_tmp), str(marker))
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = self.runner([python, "-m", "venv", str(target)], capture_output=True,
                                 text=True, timeout=300, check=False)
            if result.returncode:
                detail = (result.stderr or result.stdout or "venv creation failed").strip()
                raise CompatibilityError("Could not create SAM's Python {} environment: {}. The previous environment was preserved at {}. Resolve the reported prerequisite, then rerun setup.".format(version, detail, backup or "no prior environment"))
            check_python(str(executable), self.manifest, self.runner)
        except Exception:
            # Preserve the failed candidate for diagnosis, but restore the
            # last working environment to its original path when possible.
            if backup and backup.exists():
                failed = target.with_name(target.name + ".failed-" +
                                          datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
                if target.exists():
                    target.rename(failed)
                backup.rename(target)
                target.with_name(target.name + ".recovery.json").unlink(missing_ok=True)
            raise
        return {"path": str(target), "python": str(executable), "created": True,
                "backup": str(backup) if backup else None,
                "detail": "Created supported Python {} environment.".format(version)}

    @staticmethod
    def restore_virtualenv(target: Path) -> dict:
        """Restore the most recent preserved venv after a failed replacement."""
        target = Path(target).expanduser().resolve()
        marker = target.with_name(target.name + ".recovery.json")
        try:
            recovery = json.loads(marker.read_text(encoding="utf-8"))
            backup = Path(recovery["backup"]).resolve()
            if Path(recovery["target"]).resolve() != target or backup.parent != target.parent or not backup.name.startswith(target.name + ".backup-"):
                raise ValueError("recovery marker paths do not match the requested environment")
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise CompatibilityError("No safe environment rollback is recorded for {}: {}".format(target, exc)) from exc
        if not backup.exists():
            raise CompatibilityError("Recorded prior environment is missing: {}".format(backup))
        failed = None
        if target.exists():
            stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            failed = target.with_name(target.name + ".failed-" + stamp)
            target.rename(failed)
        backup.rename(target)
        marker.unlink(missing_ok=True)
        return {"restored": str(target), "failed_candidate": str(failed) if failed else None,
                "detail": "Previous environment restored; failed replacement retained for diagnosis."}


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
    repair = commands.add_parser("repair-dependencies")
    repair.add_argument("--group", action="append", dest="groups", required=True)
    system_dependencies = commands.add_parser("system-dependencies")
    system_dependencies.add_argument("--group", required=True)
    system_dependencies.add_argument("--format", choices=("json", "packages", "missing"), default="json")
    step = commands.add_parser("record-step")
    step.add_argument("name")
    step.add_argument("state", choices=("started", "complete", "blocked"))
    step.add_argument("--detail", default="")
    prepare = commands.add_parser("prepare-venv")
    prepare.add_argument("--python", required=True)
    prepare.add_argument("--path", type=Path, required=True)
    restore = commands.add_parser("restore-venv")
    restore.add_argument("--path", type=Path, required=True)
    args = parser.parse_args(argv)
    manager = EnvironmentCompatibilityManager()
    if args.command == "discover":
        output = manager.discover()
    elif args.command == "capabilities":
        output = manager.capabilities()
    elif args.command == "resolve-dependencies":
        output = manager.dependency_plan(args.groups)
    elif args.command == "repair-dependencies":
        output = manager.repair_dependencies(args.groups)
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
    elif args.command == "prepare-venv":
        output = manager.prepare_virtualenv(args.python, args.path)
    elif args.command == "restore-venv":
        output = manager.restore_virtualenv(args.path)
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
