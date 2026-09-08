"""
SAMRuntime — process lifecycle, status, and health for SAM's three
standalone entry points.

Checkpoint 3 (start/stop/restart) plus Checkpoint 4 (status/health) — the
Section 11 STOPPED/STARTING/READY/DEGRADED/FAILED/STOPPING state machine
and Section 12 health wrapping live in runtime.health.status and are
exposed here as SAMRuntime.status()/health(), kept in a separate module
from pure process mechanics (Section 19/20: this class coordinates both,
but the state-machine logic itself doesn't belong mixed into spawn/signal
code).

Does not implement reasoning, planning, memory, or verification (Section
20) — it only knows how to launch a command, remember its pid, check
whether that pid is still alive and still looks like what we launched,
and interpret that (plus, for the api process, a live poll of the
existing Phase 3A health endpoint) into a status/health readout.
"""

from __future__ import annotations

import os
import platform
import signal
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from runtime.health.status import RuntimeStatus, compute_health, compute_status
from runtime.lifecycle.specs import ProcessSpec, default_specs
from runtime.lifecycle.state import (
    clear_state,
    is_pid_alive,
    pid_matches_expected,
    read_state,
    update_phase,
    write_state,
)


@dataclass
class StartResult:
    name: str
    ok: bool
    pid: int | None = None
    already_running: bool = False
    message: str = ""


@dataclass
class StopResult:
    name: str
    ok: bool
    already_stopped: bool = False
    forced: bool = False
    message: str = ""


@dataclass
class RestartResult:
    name: str
    ok: bool
    stop_result: StopResult | None = None
    start_result: StartResult | None = None
    message: str = ""


def _detect_repo_root() -> Path:
    # runtime/lifecycle/manager.py -> runtime/lifecycle -> runtime -> repo root
    return Path(__file__).resolve().parent.parent.parent


class SAMRuntime:
    def __init__(
        self,
        repo_root: Path | None = None,
        data_dir: Path | None = None,
        specs: list[ProcessSpec] | None = None,
    ):
        self.repo_root = Path(repo_root) if repo_root is not None else _detect_repo_root()
        self.data_dir = Path(data_dir) if data_dir is not None else None
        resolved_specs = specs if specs is not None else default_specs(self.repo_root)
        self._specs = {s.name: s for s in resolved_specs}

    def _spec(self, name: str) -> ProcessSpec:
        if name not in self._specs:
            raise ValueError(f"Unknown process '{name}'. Known: {sorted(self._specs)}")
        return self._specs[name]

    @property
    def process_names(self) -> list[str]:
        return sorted(self._specs)

    def is_running(self, name: str) -> bool:
        spec = self._spec(name)
        state = read_state(name, self.data_dir)
        if state is None:
            return False
        pid = state.get("pid")
        if not pid or not is_pid_alive(pid):
            return False
        return pid_matches_expected(pid, spec.cmdline_fragment)

    # ─── start ──────────────────────────────────────────────────────────

    def start(self, name: str) -> StartResult:
        spec = self._spec(name)

        if self.is_running(name):
            state = read_state(name, self.data_dir)
            return StartResult(
                name=name, ok=True, pid=state["pid"], already_running=True,
                message=f"{name} is already running (pid {state['pid']}).",
            )

        # Stale state pointing at a dead/mismatched pid — clear it before
        # starting fresh so we don't leave orphaned bookkeeping around.
        if read_state(name, self.data_dir) is not None:
            clear_state(name, self.data_dir)

        try:
            proc = subprocess.Popen(
                spec.command,
                cwd=str(spec.cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=(platform.system() != "Windows"),
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0
                ),
            )
        except OSError as e:
            message = f"Failed to launch {name}: {e}"
            write_state(name, None, spec.command, self.data_dir, phase="failed", message=message)
            return StartResult(name=name, ok=False, message=message)

        write_state(name, proc.pid, spec.command, self.data_dir, phase="starting")

        ok, message = self._wait_for_ready(proc, spec)
        if not ok:
            if proc.poll() is None:
                # Never became healthy but is still alive: it's a process
                # we just spawned in this very call, so there's no PID-reuse
                # ambiguity like there is for pids read back from a state
                # file. Clean it up rather than abandoning an orphan that
                # holds a port with nothing left tracking it.
                self._terminate_freshly_spawned(proc)
                message += " The unhealthy process has been terminated."
            # A startup failure must be explicit (Section 8) — recorded as
            # a persisted FAILED phase (Section 11), not silently cleared
            # back to indistinguishable-from-never-tried STOPPED. A later
            # start() attempt overwrites this the moment it's made.
            write_state(name, proc.pid, spec.command, self.data_dir, phase="failed", message=message)
            return StartResult(name=name, ok=False, message=message)

        update_phase(name, "ready", self.data_dir, message="")
        return StartResult(name=name, ok=True, pid=proc.pid, message=message)

    def _terminate_freshly_spawned(self, proc: subprocess.Popen, timeout: float = 5.0) -> None:
        try:
            proc.terminate()
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.wait(timeout=2.0)
            except Exception:
                pass
        except Exception:
            pass

    def _wait_for_ready(self, proc: subprocess.Popen, spec: ProcessSpec) -> tuple[bool, str]:
        deadline = time.monotonic() + spec.startup_timeout_seconds

        if spec.ready_check == "http":
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    return False, (
                        f"{spec.name} exited during startup (code {proc.returncode}). "
                        f"Output:\n{self._read_tail_if_exited(proc)}"
                    )
                try:
                    with urllib.request.urlopen(spec.health_url, timeout=1.0) as resp:
                        if resp.status < 500:
                            return True, f"{spec.name} is ready (pid {proc.pid})."
                except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                    pass
                time.sleep(0.3)
            return False, (
                f"{spec.name} did not become healthy within "
                f"{spec.startup_timeout_seconds}s polling {spec.health_url}. "
                f"It may still be starting, or the port may be in use by "
                f"something else — check manually before retrying."
            )

        if spec.ready_check == "alive_after_grace":
            time.sleep(spec.grace_seconds)
            if proc.poll() is not None:
                return False, (
                    f"{spec.name} exited during startup (code {proc.returncode}). "
                    f"Output:\n{self._read_tail_if_exited(proc)}"
                )
            return True, (
                f"{spec.name} is running (pid {proc.pid}). Note: {spec.name} exposes no "
                f"health endpoint today, so this only confirms it didn't crash within "
                f"{spec.grace_seconds}s — see Checkpoint 1 audit."
            )

        return False, f"Unknown ready_check '{spec.ready_check}' for {spec.name}."

    def _read_tail_if_exited(self, proc: subprocess.Popen, max_lines: int = 20) -> str:
        # Only ever called after proc.poll() is not None, so the pipe has
        # already closed on the child's side and this read reliably hits
        # EOF rather than blocking.
        if proc.poll() is None:
            return "(process is still running; not reading output to avoid blocking)"
        try:
            remaining = proc.stdout.read() if proc.stdout else ""
        except Exception:
            remaining = ""
        lines = (remaining or "").splitlines()
        return "\n".join(lines[-max_lines:]) if lines else "(no output captured)"

    # ─── stop ───────────────────────────────────────────────────────────

    def stop(self, name: str, timeout: float | None = None) -> StopResult:
        spec = self._spec(name)
        state = read_state(name, self.data_dir)

        if state is None:
            return StopResult(
                name=name, ok=True, already_stopped=True,
                message=f"{name} has no recorded state — treating as already stopped.",
            )

        pid = state.get("pid")
        if not pid or not is_pid_alive(pid):
            clear_state(name, self.data_dir)
            return StopResult(
                name=name, ok=True, already_stopped=True,
                message=f"{name} was not running (stale state cleared).",
            )

        if not pid_matches_expected(pid, spec.cmdline_fragment):
            return StopResult(
                name=name, ok=False,
                message=(
                    f"Refusing to stop pid {pid}: it no longer looks like '{name}' "
                    f"(expected '{spec.cmdline_fragment}' in its command line). The "
                    f"recorded pid may have been reused by an unrelated process — not "
                    f"signaling it. Clear the state file manually if you're sure it's safe "
                    f"(Section 7: don't terminate arbitrary processes)."
                ),
            )

        deadline_seconds = timeout if timeout is not None else spec.shutdown_timeout_seconds
        update_phase(name, "stopping", self.data_dir)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            clear_state(name, self.data_dir)
            return StopResult(
                name=name, ok=True, already_stopped=True,
                message=f"{name} exited before the stop signal was sent.",
            )
        except PermissionError as e:
            return StopResult(name=name, ok=False, message=f"No permission to stop {name} (pid {pid}): {e}")

        deadline = time.monotonic() + deadline_seconds
        while time.monotonic() < deadline:
            if not is_pid_alive(pid):
                clear_state(name, self.data_dir)
                return StopResult(name=name, ok=True, message=f"{name} stopped gracefully (pid {pid}).")
            time.sleep(0.2)

        # Graceful shutdown didn't finish in time — escalate.
        # NOTE (Windows): os.kill(pid, SIGTERM) above already maps to
        # TerminateProcess on Windows — there is no POSIX-style graceful
        # signal delivery to an arbitrary external process there, so on
        # Windows this escalation path and the "graceful" path above are
        # not actually different in kind. Flagging honestly rather than
        # implying parity that doesn't exist (Checkpoint 1 audit).
        try:
            if platform.system() == "Windows":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
            else:
                os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

        time.sleep(0.3)
        clear_state(name, self.data_dir)
        still_alive = is_pid_alive(pid)
        return StopResult(
            name=name,
            ok=not still_alive,
            forced=True,
            message=(
                f"{name} did not stop gracefully within {deadline_seconds}s; force-killed pid {pid}."
                if not still_alive else
                f"{name} (pid {pid}) is still alive even after a forced kill."
            ),
        )

    # ─── restart ────────────────────────────────────────────────────────

    def restart(self, name: str) -> RestartResult:
        stop_result = self.stop(name)
        if not stop_result.ok:
            return RestartResult(
                name=name, ok=False, stop_result=stop_result,
                message=f"Restart aborted: could not stop {name} first.",
            )
        time.sleep(0.3)  # let a just-freed port fully release before rebinding
        start_result = self.start(name)
        return RestartResult(
            name=name, ok=start_result.ok, stop_result=stop_result,
            start_result=start_result, message=start_result.message,
        )

    # ─── status / health (Checkpoint 4) ────────────────────────────────

    def status(self, name: str) -> RuntimeStatus:
        return compute_status(self._spec(name), self.data_dir)

    def health(self, name: str) -> dict:
        return compute_health(self._spec(name), self.data_dir)

    def status_all(self) -> dict[str, RuntimeStatus]:
        return {name: self.status(name) for name in self.process_names}

    def health_all(self) -> dict[str, dict]:
        return {name: self.health(name) for name in self.process_names}

    # ─── bulk helpers ("sam start" with no argument == all three) ──────

    def start_all(self) -> dict[str, StartResult]:
        return {name: self.start(name) for name in self.process_names}

    def stop_all(self) -> dict[str, StopResult]:
        return {name: self.stop(name) for name in self.process_names}
