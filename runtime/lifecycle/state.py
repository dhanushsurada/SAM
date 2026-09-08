"""
Runtime state bookkeeping — one small JSON file per managed process.

Location: ~/.sam_data/runtime/<name>.json by default.

Checkpoint 2 design note (deviation from Phase 3B Section 7's default
preference): Section 7 says avoid ~/.sam_data/ for runtime state "unless
there is a strong reason." The reason here is consistency: every other
piece of SAM's persistent state already lives under ~/.sam_data/
(~/.sam_data/iqoo/tasks.db, ~/.sam_data/ecosystem/devices.db,
~/.sam_data/settings.yaml, Settings.log_path). Putting runtime state
anywhere else would be the one exception to an otherwise uniform
convention. runtime/ gets its own clearly-separated subfolder
(~/.sam_data/runtime/) rather than mixing state files in with any
existing directory, which satisfies Section 7's "prefer clearly separated
runtime state" while staying consistent with the rest of SAM.

No new dependency was added for process introspection (no psutil). PID
liveness and command-line lookups use stdlib + subprocess, following the
same platform-branch pattern config/settings.py already uses for hardware
detection (sysctl on macOS, wmic on Windows). This was a judgment call
flagged in the Checkpoint 1 audit and Checkpoint 2 design as open for
reconsideration.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path

DEFAULT_SAM_DATA_DIR = Path.home() / ".sam_data"


def runtime_state_dir(data_dir: Path | None = None) -> Path:
    base = Path(data_dir) if data_dir is not None else DEFAULT_SAM_DATA_DIR
    return base / "runtime"


def _state_path(name: str, data_dir: Path | None = None) -> Path:
    return runtime_state_dir(data_dir) / f"{name}.json"


def write_state(
    name: str,
    pid: int | None,
    command: list[str],
    data_dir: Path | None = None,
    phase: str = "ready",
    message: str = "",
) -> None:
    path = _state_path(name, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": name,
        "pid": pid,
        "command": command,
        "started_at": time.time(),
        "phase": phase,  # "starting" | "ready" | "stopping" | "failed"
        "message": message,
    }
    path.write_text(json.dumps(payload, indent=2))


def update_phase(name: str, phase: str, data_dir: Path | None = None, message: str | None = None) -> bool:
    """Update just the phase (and optionally message) of an existing state
    file, preserving pid/command/started_at. Returns False if there's no
    existing state file to update — callers should treat that as a no-op,
    not an error, since it just means the process was never started or was
    already cleared."""
    existing = read_state(name, data_dir)
    if existing is None:
        return False
    existing["phase"] = phase
    if message is not None:
        existing["message"] = message
    _state_path(name, data_dir).write_text(json.dumps(existing, indent=2))
    return True


def read_state(name: str, data_dir: Path | None = None) -> dict | None:
    path = _state_path(name, data_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable state file — treat as "no reliable state"
        # rather than raising. Section 21 explicitly calls out "stale
        # PID/state" as a case that must be handled, not crash on.
        return None


def clear_state(name: str, data_dir: Path | None = None) -> None:
    _state_path(name, data_dir).unlink(missing_ok=True)


def _reap_if_own_child(pid: int) -> None:
    """Best-effort: if `pid` is a direct child of the calling process and
    has already exited, reap it so it doesn't linger as a zombie and make
    a signaled-but-unreaped process look "alive" to kill(pid, 0). No-op if
    we're not its parent (ChildProcessError) — the common case once a
    separate CLI invocation's process has exited and the OS has reparented
    the child elsewhere. This matters here specifically because
    SAMRuntime.restart() calls stop() then start() within one process, so
    a process it just spawned earlier in the same run IS its own child."""
    try:
        os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, OSError):
        return


def is_pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if platform.system() == "Windows":
        return _is_pid_alive_windows(pid)
    _reap_if_own_child(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists, just not signalable by us (owned by another user). Still
        # "alive" for our purposes — we just may not be able to stop it.
        return True
    else:
        return True


def _is_pid_alive_windows(pid: int) -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return False
    return str(pid) in result.stdout


def cmdline_for_pid(pid: int) -> str:
    """Best-effort. Returns '' if it can't be determined (permissions,
    platform quirk, process already gone) rather than raising."""
    if platform.system() == "Windows":
        return _cmdline_windows(pid)
    proc_path = Path(f"/proc/{pid}/cmdline")
    if proc_path.exists():
        try:
            raw = proc_path.read_bytes()
            return raw.replace(b"\x00", b" ").decode(errors="replace").strip()
        except OSError:
            pass
    # macOS (and any POSIX without /proc) fallback.
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _cmdline_windows(pid: int) -> str:
    try:
        result = subprocess.run(
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine"],
            capture_output=True, text=True, timeout=5,
        )
        lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        return lines[1] if len(lines) > 1 else ""
    except Exception:
        return ""


def pid_matches_expected(pid: int, fragment: str) -> bool:
    """Safety check before signaling a pid read back from a state file.
    Fails OPEN (returns True) if the command line can't be determined at
    all, rather than blocking a legitimate stop/restart on a platform quirk
    — this is a best-effort guard against PID reuse, not a hard guarantee."""
    if not fragment:
        return True
    cmdline = cmdline_for_pid(pid)
    if not cmdline:
        return True
    return fragment in cmdline
