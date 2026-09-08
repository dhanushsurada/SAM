"""
Runtime status + health — Checkpoint 4.

Deliberately separate from runtime/lifecycle/, which only knows how to
spawn/signal/track processes. This module interprets that raw state
(plus, for the api process, a live poll of the *existing* Phase 3A health
endpoint) into the Section 11 status vocabulary and a Section 12 health
dict.

It reuses interfaces/api/gateway.py's existing TaskGateway.health()
semantics for the api process rather than re-implementing them: the
Checkpoint 1 audit found that health() already treats vision/whisper
availability as informational-only and doesn't fold them into its
ok/degraded computation — exactly the "optional capability down != runtime
failed" behavior Section 12 asks for. This module does not duplicate that
logic; it asks the running process for it over HTTP (the same endpoint a
phone client would hit) and layers a process-level view on top.

voice and telegram expose no queryable health today (Checkpoint 1 audit).
Their status/health is intentionally thinner — process_alive and
uptime_seconds only — rather than inventing a deeper signal that doesn't
actually exist. This is a limitation of those two processes, not a gap in
this module.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from enum import Enum

from runtime.lifecycle.specs import ProcessSpec
from runtime.lifecycle.state import is_pid_alive, pid_matches_expected, read_state


class RuntimeStatus(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    STOPPING = "STOPPING"


def _poll_health_endpoint(url: str, timeout: float = 2.0) -> dict | None:
    """Live GET against an existing health endpoint. None if unreachable —
    process alive but not answering, wrong port, etc. — never raises."""
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, ValueError):
        return None


def _alive_and_ours(state: dict, spec: ProcessSpec) -> bool:
    pid = state.get("pid")
    return bool(pid) and is_pid_alive(pid) and pid_matches_expected(pid, spec.cmdline_fragment)


def compute_status(spec: ProcessSpec, data_dir=None) -> RuntimeStatus:
    state = read_state(spec.name, data_dir)
    if state is None:
        return RuntimeStatus.STOPPED

    phase = state.get("phase", "ready")

    if phase == "failed":
        # A start attempt was made and didn't succeed. Persists until the
        # next start() attempt overwrites it — Section 11 wants this
        # distinguishable from "never tried" STOPPED, not collapsed into it.
        return RuntimeStatus.FAILED

    alive = _alive_and_ours(state, spec)

    if phase == "starting":
        # Normally only observable by a *concurrent* status() call while
        # another start() is still in its readiness wait, since start()
        # itself resolves this to "ready" or "failed" before returning.
        # If the pid is already gone here, something died between writing
        # this phase and being checked (e.g. the starting process itself
        # was killed) — that's a failure, not a still-in-progress start.
        return RuntimeStatus.STARTING if alive else RuntimeStatus.FAILED

    if phase == "stopping":
        return RuntimeStatus.STOPPING if alive else RuntimeStatus.STOPPED

    # phase == "ready" (or an older state file predating this field).
    if not alive:
        return RuntimeStatus.STOPPED

    if spec.ready_check == "http":
        health = _poll_health_endpoint(spec.health_url)
        if health is None:
            # Alive but not answering its own health endpoint — something
            # is wrong short of the process having actually died.
            return RuntimeStatus.DEGRADED
        return RuntimeStatus.READY if health.get("status") == "ok" else RuntimeStatus.DEGRADED

    # alive_after_grace processes (voice, telegram): no health endpoint
    # exists to ask — this is the honest floor from the Checkpoint 1 audit,
    # not a gap in this function.
    return RuntimeStatus.READY


def compute_health(spec: ProcessSpec, data_dir=None) -> dict:
    state = read_state(spec.name, data_dir)
    status = compute_status(spec, data_dir)

    result = {
        "name": spec.name,
        "runtime_status": status.value,
        "process_alive": status not in (RuntimeStatus.STOPPED, RuntimeStatus.FAILED),
        "pid": (state or {}).get("pid"),
        "uptime_seconds": (time.time() - state["started_at"]) if state and state.get("pid") else None,
    }
    if state and state.get("phase") == "failed" and state.get("message"):
        result["last_failure"] = state["message"]

    if spec.ready_check == "http" and result["process_alive"]:
        live_health = _poll_health_endpoint(spec.health_url)
        if live_health is not None:
            # Merge the existing Phase 3A health dict in directly instead
            # of re-deriving worker_alive/vision_model_available/etc.
            # ourselves — Section 12: reuse, don't duplicate.
            result["gateway_health"] = live_health
        else:
            result["gateway_health"] = None
            result["note"] = "process is alive but its health endpoint is not responding"
    elif spec.ready_check == "alive_after_grace":
        result["note"] = (
            f"{spec.name} exposes no health endpoint today — this reflects only "
            f"whether the process is alive, not whether it's actually working "
            f"(see Checkpoint 1 audit)."
        )

    return result
