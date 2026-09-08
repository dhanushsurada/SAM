"""
ProcessSpec — describes how to launch one of SAM's standalone processes and
how to recognize when it has come up.

Deliberately NOT coupled to vivo/iQOO, Telegram, or web-UI specifics beyond
"here is the command to run and here is how to tell if it's ready" (Phase 3B
Sections 6, 19: runtime must stay generic SAM infrastructure).

Audit findings (Checkpoint 1) this file encodes directly:
  - voice (main.py) and telegram (interfaces/telegram/telegram_bridge.py)
    expose no health endpoint and no queryable readiness signal today. The
    only honest ready-check for them is "still alive after a short grace
    period" — NOT a real health check. See runtime/lifecycle/manager.py's
    _wait_for_ready() for exactly what this does and does not guarantee.
  - api (interfaces/api/server.py) has a real health endpoint at
    /api/iqoo/health. Host/port are sourced from config/settings.py
    (Settings().api_host / .api_port, default 0.0.0.0:8420) — this spec's
    health_url is built from that same Settings().api_port at call time
    below, so it cannot independently drift from what the server actually
    binds. (Previously a literal here; centralized post-Checkpoint-7 audit.)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessSpec:
    name: str  # "voice" | "api" | "telegram" — also the state-file key
    command: list[str]  # argv, e.g. [sys.executable, "-m", "interfaces.api.server"]
    cwd: Path
    ready_check: str  # "http" | "alive_after_grace"
    health_url: str = ""  # required if ready_check == "http"
    grace_seconds: float = 2.0  # used if ready_check == "alive_after_grace"
    startup_timeout_seconds: float = 15.0
    shutdown_timeout_seconds: float = 10.0
    # A short, distinctive fragment expected in the *running* process's own
    # command line. Checked before this runtime ever signals a pid it read
    # back from a state file, to guard against PID reuse — Phase 3B Section 7:
    # "Avoid unsafe process killing ... use a controlled SAM-owned process
    # model." This is a sanity check, not a security boundary.
    cmdline_fragment: str = ""


def default_specs(repo_root: Path) -> list[ProcessSpec]:
    """The three real SAM entry points, confirmed against the actual code
    in Checkpoint 1 (main.py, interfaces/api/server.py,
    interfaces/telegram/telegram_bridge.py). `repo_root` is the directory
    containing main.py / interfaces/ / etc., so this works regardless of
    the caller's own current working directory."""
    repo_root = Path(repo_root)
    from config.settings import Settings
    api_port = Settings().api_port
    return [
        ProcessSpec(
            name="voice",
            command=[sys.executable, "main.py"],
            cwd=repo_root,
            ready_check="alive_after_grace",
            grace_seconds=2.0,
            startup_timeout_seconds=10.0,
            shutdown_timeout_seconds=10.0,
            cmdline_fragment="main.py",
        ),
        ProcessSpec(
            name="api",
            command=[sys.executable, "-m", "interfaces.api.server"],
            cwd=repo_root,
            ready_check="http",
            health_url=f"http://127.0.0.1:{api_port}/api/iqoo/health",
            startup_timeout_seconds=15.0,
            shutdown_timeout_seconds=10.0,
            cmdline_fragment="interfaces.api.server",
        ),
        ProcessSpec(
            name="telegram",
            command=[sys.executable, "-m", "interfaces.telegram.telegram_bridge"],
            cwd=repo_root,
            ready_check="alive_after_grace",
            grace_seconds=2.0,
            startup_timeout_seconds=10.0,
            shutdown_timeout_seconds=10.0,
            cmdline_fragment="interfaces.telegram.telegram_bridge",
        ),
    ]
