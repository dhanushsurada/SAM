"""Detect and optionally start Ollama without claiming ownership of it.

SAMRuntime manages SAM-owned processes. Ollama may be shared with other
applications, so this manager detects it and can start it, but deliberately
does not expose a stop operation or persist a process ID.
"""

from __future__ import annotations

import ipaddress
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

from runtime.health.status import RuntimeStatus

TAGS_TIMEOUT_S = 3.0


def _known_ollama_locations() -> list[Path]:
    """Where the official installers put Ollama. Needed because a process that
    was already running when Ollama was installed keeps its old PATH and
    would otherwise report "not installed" right after a successful install."""
    system = platform.system()
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        candidates = []
        if local:
            candidates.append(Path(local) / "Programs" / "Ollama" / "ollama.exe")
        program_files = os.environ.get("ProgramFiles")
        if program_files:
            candidates.append(Path(program_files) / "Ollama" / "ollama.exe")
        return candidates
    if system == "Darwin":
        return [
            Path("/Applications/Ollama.app/Contents/Resources/ollama"),
            Path.home() / "Applications/Ollama.app/Contents/Resources/ollama",
            Path("/opt/homebrew/bin/ollama"),
            Path("/usr/local/bin/ollama"),
        ]
    return [Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama"), Path("/opt/ollama/bin/ollama")]


def find_ollama_executable() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    for candidate in _known_ollama_locations():
        if candidate.is_file():
            return str(candidate)
    return None


class OllamaManager:
    def __init__(self, host: str = "http://localhost:11434"):
        self.host = str(host).rstrip("/")

    def _tags(self) -> list[dict]:
        response = requests.get(f"{self.host}/api/tags", timeout=TAGS_TIMEOUT_S)
        if response.status_code != 200:
            raise RuntimeError(f"Ollama answered HTTP {response.status_code}")
        payload = response.json()
        models = payload.get("models", []) if isinstance(payload, dict) else []
        if not isinstance(models, list) or any(not isinstance(item, dict) for item in models):
            raise ValueError("Ollama returned an invalid model list")
        return models

    def _is_local_host(self) -> bool:
        try:
            hostname = urlsplit(self.host).hostname
            if hostname == "localhost":
                return True
            return bool(hostname and ipaddress.ip_address(hostname).is_loopback)
        except ValueError:
            return False

    def status(self) -> dict:
        try:
            models = self._tags()
            names = [item.get("name") or item.get("model") for item in models]
            names = [name for name in names if isinstance(name, str)]
            return {
                "state": RuntimeStatus.READY.value,
                "detail": f"{len(names)} model(s) pulled",
                "models": names,
            }
        except Exception:
            if not self._is_local_host():
                return {
                    "state": RuntimeStatus.STOPPED.value,
                    "detail": f"configured Ollama endpoint is not responding at {self.host}",
                    "models": [],
                }
            if find_ollama_executable() is None:
                return {
                    "state": RuntimeStatus.NOT_INSTALLED.value,
                    "detail": "the `ollama` executable was not found on PATH",
                    "models": [],
                }
            return {
                "state": RuntimeStatus.STOPPED.value,
                "detail": f"installed but not responding at {self.host}",
                "models": [],
            }

    def start(self, timeout_s: float = 15.0) -> dict:
        current = self.status()
        if current["state"] == RuntimeStatus.READY.value:
            return {"ok": True, "already_running": True, "message": "Ollama is already running."}
        if current["state"] == RuntimeStatus.NOT_INSTALLED.value:
            return {
                "ok": False,
                "already_running": False,
                "message": "Ollama is not installed; install it using the supported setup procedure.",
            }
        if not self._is_local_host():
            return {
                "ok": False,
                "already_running": False,
                "message": f"SAM cannot start Ollama configured at non-local host {self.host}.",
            }

        executable = find_ollama_executable() or "ollama"
        try:
            popen_kwargs: dict = {"start_new_session": True}
            if platform.system() == "Windows":
                # No console window flash; detach from this process group.
                popen_kwargs = {"creationflags": 0x08000000 | 0x00000200}
            subprocess.Popen(
                [executable, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **popen_kwargs,
            )
        except OSError as e:
            return {"ok": False, "already_running": False, "message": f"could not launch Ollama: {e}"}

        deadline = time.monotonic() + max(0.0, timeout_s)
        while time.monotonic() < deadline:
            if self.status()["state"] == RuntimeStatus.READY.value:
                return {"ok": True, "already_running": False, "message": "Ollama started."}
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
        return {
            "ok": False,
            "already_running": False,
            "message": f"Ollama did not become ready within {timeout_s:.0f}s.",
        }
