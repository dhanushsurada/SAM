"""
OFFLINE status/health test suite — Phase 3B, Checkpoint 4.

Verifies runtime.health.status.compute_status()/compute_health() against
throwaway dummy processes and hand-written state files — not the real
main.py / interfaces.api.server / interfaces.telegram.telegram_bridge.
Everything runs against a temp data_dir; ~/.sam_data is never touched.

Usage:
    python3 tests/test_runtime_health_offline.py
"""

import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
REPO_ROOT = Path(__file__).parent.parent

from runtime.health.status import RuntimeStatus, compute_health, compute_status
from runtime.lifecycle.manager import SAMRuntime
from runtime.lifecycle.specs import ProcessSpec
from runtime.lifecycle.state import is_pid_alive, write_state

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(bool(condition))
    print(f"[{status}] {label}")


# ─── fixtures ───────────────────────────────────────────────────────────

FIXTURE_DIR = Path(tempfile.mkdtemp(prefix="sam_runtime_health_test_fixtures_"))

SLEEPER = FIXTURE_DIR / "sleeper.py"
SLEEPER.write_text("import time\ntime.sleep(120)\n")

SLOW_STOPPER = FIXTURE_DIR / "slow_stopper.py"
SLOW_STOPPER.write_text(
    "import signal, time, sys\n"
    "def _graceful(signum, frame):\n"
    "    time.sleep(1.5)\n"
    "    sys.exit(0)\n"
    "signal.signal(signal.SIGTERM, _graceful)\n"
    "time.sleep(120)\n"
)


def _health_server_src(status_value):
    return (
        "import sys\n"
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "port = int(sys.argv[1])\n"
        "class H(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200)\n"
        "        self.end_headers()\n"
        f"        self.wfile.write(b'{{\"status\":\"{status_value}\"}}')\n"
        "    def log_message(self, *a):\n"
        "        pass\n"
        "HTTPServer(('127.0.0.1', port), H).serve_forever()\n"
    )


HEALTH_OK = FIXTURE_DIR / "health_ok.py"
HEALTH_OK.write_text(_health_server_src("ok"))

HEALTH_DEGRADED = FIXTURE_DIR / "health_degraded.py"
HEALTH_DEGRADED.write_text(_health_server_src("degraded"))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def new_runtime(specs):
    tmp = Path(tempfile.mkdtemp(prefix="sam_runtime_health_test_data_"))
    return SAMRuntime(repo_root=REPO_ROOT, data_dir=tmp, specs=specs), tmp


def http_spec(name, port, script=HEALTH_OK, startup_timeout=5.0):
    return ProcessSpec(
        name=name, command=[sys.executable, str(script), str(port)], cwd=FIXTURE_DIR,
        ready_check="http", health_url=f"http://127.0.0.1:{port}/",
        startup_timeout_seconds=startup_timeout, shutdown_timeout_seconds=5.0,
        cmdline_fragment=script.name,
    )


def sleeper_spec(name="voice", command_path=SLEEPER, shutdown_timeout=5.0):
    return ProcessSpec(
        name=name, command=[sys.executable, str(command_path)], cwd=FIXTURE_DIR,
        ready_check="alive_after_grace", grace_seconds=0.5,
        startup_timeout_seconds=5.0, shutdown_timeout_seconds=shutdown_timeout,
        cmdline_fragment=command_path.name,
    )


# ─── A: the basic states ────────────────────────────────────────────────

def test_stopped_when_never_started():
    spec = sleeper_spec()
    rt, tmp = new_runtime([spec])
    try:
        check("status() is STOPPED when there's no state file at all", rt.status("voice") == RuntimeStatus.STOPPED)
        health = rt.health("voice")
        check("health() agrees: process_alive is False", health["process_alive"] is False)
        check("health() reports no pid when never started", health["pid"] is None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ready_for_healthy_http_process():
    port = free_port()
    spec = http_spec("api", port, script=HEALTH_OK)
    rt, tmp = new_runtime([spec])
    try:
        rt.start("api")
        check("status() is READY once the health endpoint says ok", rt.status("api") == RuntimeStatus.READY)
        health = rt.health("api")
        check("health() merges the live gateway_health dict in directly", health.get("gateway_health", {}).get("status") == "ok")
        check("health() reports a positive uptime once running", health["uptime_seconds"] is not None and health["uptime_seconds"] >= 0)
        rt.stop("api")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_degraded_when_health_endpoint_says_degraded():
    port = free_port()
    spec = http_spec("api", port, script=HEALTH_DEGRADED)
    rt, tmp = new_runtime([spec])
    try:
        rt.start("api")
        check("status() is DEGRADED when the process's own health says degraded", rt.status("api") == RuntimeStatus.DEGRADED)
        rt.stop("api")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_degraded_when_alive_but_unreachable():
    # A real, alive process that matches the identity check but simply
    # doesn't run an HTTP server — isolates "alive and confirmed ours, but
    # not answering health" from the cmdline-mismatch case, which is a
    # different scenario already covered in test_runtime_lifecycle_offline.py.
    bystander = subprocess.Popen([sys.executable, str(SLEEPER)], cwd=str(FIXTURE_DIR))
    try:
        time.sleep(0.3)
        port = free_port()
        spec = ProcessSpec(
            name="api", command=[sys.executable, str(SLEEPER)], cwd=FIXTURE_DIR,
            ready_check="http", health_url=f"http://127.0.0.1:{port}/",
            startup_timeout_seconds=5.0, shutdown_timeout_seconds=5.0,
            cmdline_fragment="sleeper.py",  # matches the bystander's real cmdline
        )
        rt, tmp = new_runtime([spec])
        write_state("api", bystander.pid, spec.command, tmp, phase="ready")
        check(
            "status() is DEGRADED (not READY, not STOPPED) when alive but unreachable",
            compute_status(spec, tmp) == RuntimeStatus.DEGRADED,
        )
        shutil.rmtree(tmp, ignore_errors=True)
    finally:
        bystander.terminate()
        bystander.wait(timeout=5)


def test_failed_persists_and_is_queryable():
    # SLEEPER opens no port at all, so an http-style health check against it
    # is guaranteed to time out rather than possibly racing a real server.
    port = free_port()
    spec = ProcessSpec(
        name="api", command=[sys.executable, str(SLEEPER)], cwd=FIXTURE_DIR,
        ready_check="http", health_url=f"http://127.0.0.1:{port}/",
        startup_timeout_seconds=1.0, shutdown_timeout_seconds=5.0,
        cmdline_fragment="sleeper.py",
    )
    rt, tmp = new_runtime([spec])
    try:
        rt.start("api")
        check("status() is FAILED after a start attempt that never became healthy", rt.status("api") == RuntimeStatus.FAILED)
        health = rt.health("api")
        check("health() surfaces the failure message for a FAILED process", "last_failure" in health and bool(health["last_failure"]))
        check("health() reports process_alive False for a FAILED process", health["process_alive"] is False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─── B: transient states observed by a concurrent caller ───────────────

def test_starting_is_observable_concurrently():
    # A health server that only opens its port after a deliberate delay,
    # so a concurrent status() call has a real window to observe STARTING.
    delayed = FIXTURE_DIR / "delayed_health.py"
    delayed.write_text(
        "import sys, time\n"
        "time.sleep(2.0)\n"
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "port = int(sys.argv[1])\n"
        "class H(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200)\n"
        "        self.end_headers()\n"
        "        self.wfile.write(b'{\"status\":\"ok\"}')\n"
        "    def log_message(self, *a):\n"
        "        pass\n"
        "HTTPServer(('127.0.0.1', port), H).serve_forever()\n"
    )
    port = free_port()
    spec = http_spec("api", port, script=delayed, startup_timeout=8.0)
    rt, tmp = new_runtime([spec])
    observed = {}

    def _start():
        observed["result"] = rt.start("api")

    t = threading.Thread(target=_start)
    t.start()
    time.sleep(0.7)  # well inside the 2s delay, after the state file is written
    mid_flight_status = rt.status("api")
    t.join(timeout=10)

    try:
        check("status() observes STARTING from a separate call while start() is still waiting", mid_flight_status == RuntimeStatus.STARTING)
        check("the start() call itself still succeeds once the delay passes", observed.get("result") is not None and observed["result"].ok)
        rt.stop("api")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_stopping_is_observable_concurrently():
    spec = sleeper_spec(name="voice", command_path=SLOW_STOPPER, shutdown_timeout=5.0)
    rt, tmp = new_runtime([spec])
    try:
        rt.start("voice")
        observed = {}

        def _stop():
            observed["result"] = rt.stop("voice")

        t = threading.Thread(target=_stop)
        t.start()
        time.sleep(0.4)  # inside SLOW_STOPPER's 1.5s graceful-exit delay
        mid_flight_status = rt.status("voice")
        t.join(timeout=10)

        check("status() observes STOPPING from a separate call while stop() is still waiting", mid_flight_status == RuntimeStatus.STOPPING)
        check("the stop() call itself still succeeds once the process exits", observed.get("result") is not None and observed["result"].ok)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─── C: no health endpoint (voice/telegram) — honest, not invented ──────

def test_alive_after_grace_has_no_fake_health():
    spec = sleeper_spec(name="voice")
    rt, tmp = new_runtime([spec])
    try:
        rt.start("voice")
        check("a process with no health endpoint is READY once merely alive", rt.status("voice") == RuntimeStatus.READY)
        health = rt.health("voice")
        check("health() does not fabricate a gateway_health dict that doesn't exist", "gateway_health" not in health)
        check("health() is honest about the limitation via a note", "note" in health and "no health endpoint" in health["note"])
        rt.stop("voice")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─── D: bulk helpers ─────────────────────────────────────────────────────

def test_status_all_and_health_all():
    voice = sleeper_spec(name="voice")
    api = http_spec("api", free_port())
    rt, tmp = new_runtime([voice, api])
    try:
        rt.start_all()
        statuses = rt.status_all()
        check("status_all() covers every configured process", set(statuses) == {"voice", "api"})
        check("status_all() reports both as up", statuses["voice"] == RuntimeStatus.READY and statuses["api"] == RuntimeStatus.READY)
        healths = rt.health_all()
        check("health_all() covers every configured process", set(healths) == {"voice", "api"})
        rt.stop_all()
        check("status_all() reports both stopped after stop_all()", all(s == RuntimeStatus.STOPPED for s in rt.status_all().values()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("=== A: the basic states ===")
    test_stopped_when_never_started()
    test_ready_for_healthy_http_process()
    test_degraded_when_health_endpoint_says_degraded()
    test_degraded_when_alive_but_unreachable()
    test_failed_persists_and_is_queryable()

    print("\n=== B: transient states observed concurrently ===")
    test_starting_is_observable_concurrently()
    test_stopping_is_observable_concurrently()

    print("\n=== C: no health endpoint is represented honestly ===")
    test_alive_after_grace_has_no_fake_health()

    print("\n=== D: bulk helpers ===")
    test_status_all_and_health_all()

    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("All runtime.health offline checks passed.")
    print(
        "NOTE: exercises compute_status()/compute_health() against throwaway dummy "
        "scripts and hand-written state files only. Never touches the real "
        "main.py, interfaces.api.server, or interfaces.telegram.telegram_bridge, "
        "and never touches ~/.sam_data. sam doctor (Section 13) is explicitly "
        "deferred to Checkpoint 5 (CLI integration), not covered here."
    )


if __name__ == "__main__":
    main()
