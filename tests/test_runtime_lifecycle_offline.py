"""
OFFLINE lifecycle test suite — Phase 3B, Checkpoint 3.

Verifies runtime.lifecycle.SAMRuntime's start/stop/restart mechanics against
small throwaway dummy scripts, NOT the real main.py / interfaces.api.server /
interfaces.telegram.telegram_bridge — those need the full dependency stack
(Ollama, faster-whisper, playwright, python-telegram-bot), none of which this
suite requires or touches. Real-process behavior is therefore UNVERIFIED by
this suite; see docs/iqoo/ (Checkpoint 1 audit notes) for what each real
process's actual readiness signal is and isn't.

Every SAMRuntime instance here is given an explicit temp data_dir, so
~/.sam_data is never read or written regardless of environment. No real SAM
process is ever spawned or signaled.

Usage:
    python3 tests/test_runtime_lifecycle_offline.py
"""

import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
REPO_ROOT = Path(__file__).parent.parent

from runtime.health.status import RuntimeStatus, compute_status
from runtime.lifecycle.manager import SAMRuntime
from runtime.lifecycle.specs import ProcessSpec
from runtime.lifecycle.state import is_pid_alive, read_state, write_state

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(bool(condition))
    print(f"[{status}] {label}")


# ─── fixtures: tiny throwaway scripts — never SAM's real entry points ──

FIXTURE_DIR = Path(tempfile.mkdtemp(prefix="sam_runtime_test_fixtures_"))

SLEEPER = FIXTURE_DIR / "sleeper.py"
SLEEPER.write_text("import time\ntime.sleep(120)\n")

FAILER = FIXTURE_DIR / "failer.py"
FAILER.write_text(
    "import sys\n"
    "print('simulated startup failure: config invalid', flush=True)\n"
    "sys.exit(1)\n"
)

HEALTH_SERVER = FIXTURE_DIR / "health_server.py"
HEALTH_SERVER.write_text(
    "import sys\n"
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


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def new_runtime(specs):
    tmp = Path(tempfile.mkdtemp(prefix="sam_runtime_test_data_"))
    return SAMRuntime(repo_root=REPO_ROOT, data_dir=tmp, specs=specs), tmp


def sleeper_spec(name="dummy_sleep", fragment="sleeper.py"):
    return ProcessSpec(
        name=name, command=[sys.executable, str(SLEEPER)], cwd=FIXTURE_DIR,
        ready_check="alive_after_grace", grace_seconds=0.5,
        startup_timeout_seconds=5.0, shutdown_timeout_seconds=5.0,
        cmdline_fragment=fragment,
    )


def failer_spec(name="dummy_fail"):
    return ProcessSpec(
        name=name, command=[sys.executable, str(FAILER)], cwd=FIXTURE_DIR,
        ready_check="alive_after_grace", grace_seconds=0.5,
        startup_timeout_seconds=5.0, shutdown_timeout_seconds=5.0,
        cmdline_fragment="failer.py",
    )


def http_spec(name, port):
    return ProcessSpec(
        name=name, command=[sys.executable, str(HEALTH_SERVER), str(port)], cwd=FIXTURE_DIR,
        ready_check="http", health_url=f"http://127.0.0.1:{port}/",
        startup_timeout_seconds=5.0, shutdown_timeout_seconds=5.0,
        cmdline_fragment="health_server.py",
    )


def unreachable_http_spec(name, port):
    # Comes up fine but never opens the health port — simulates a hung or
    # misconfigured start, or a port something else already holds.
    return ProcessSpec(
        name=name, command=[sys.executable, str(SLEEPER)], cwd=FIXTURE_DIR,
        ready_check="http", health_url=f"http://127.0.0.1:{port}/",
        startup_timeout_seconds=1.5, shutdown_timeout_seconds=5.0,
        cmdline_fragment="sleeper.py",
    )


# ─── A: start / stop / idempotency ─────────────────────────────────────

def test_start_and_stop_alive_after_grace():
    rt, tmp = new_runtime([sleeper_spec()])
    try:
        result = rt.start("dummy_sleep")
        check("start() succeeds for a process with no health endpoint", result.ok)
        check("start() reports a real, live pid", bool(result.pid) and is_pid_alive(result.pid))

        again = rt.start("dummy_sleep")
        check("start() is idempotent: already_running instead of double-spawning", again.already_running)
        check("start() idempotency doesn't change the tracked pid", again.pid == result.pid)

        stop_result = rt.stop("dummy_sleep")
        check("stop() succeeds against a running process", stop_result.ok)
        check("stop() confirms the pid is actually gone", not is_pid_alive(result.pid))
        check("stop() clears the state file on success", read_state("dummy_sleep", tmp) is None)

        second_stop = rt.stop("dummy_sleep")
        check("stop() on an already-stopped process reports already_stopped", second_stop.already_stopped)
        check("stop() on an already-stopped process still reports ok", second_stop.ok)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_start_failure_is_explicit():
    rt, tmp = new_runtime([failer_spec()])
    try:
        result = rt.start("dummy_fail")
        check("start() reports failure when the process exits immediately", not result.ok)
        check("failure message captures the process's own output", "simulated startup failure" in result.message)
        state = read_state("dummy_fail", tmp)
        check("a failed start persists a FAILED-phase record instead of vanishing", state is not None and state.get("phase") == "failed")
        check("status() reports FAILED, distinct from never-having-tried STOPPED", compute_status(failer_spec(), tmp) == RuntimeStatus.FAILED)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_http_ready_check_success():
    port = free_port()
    rt, tmp = new_runtime([http_spec("dummy_api", port)])
    try:
        result = rt.start("dummy_api")
        check("start() with an http ready_check succeeds once the health endpoint responds", result.ok)
        rt.stop("dummy_api")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_http_ready_check_timeout_cleans_up():
    port = free_port()  # deliberately never opened by the spawned process
    spec = unreachable_http_spec("dummy_hung", port)
    rt, tmp = new_runtime([spec])
    try:
        started = time.monotonic()
        result = rt.start("dummy_hung")
        elapsed = time.monotonic() - started
        check("start() with an unresponsive health endpoint times out rather than hanging", not result.ok)
        check("the timeout resolves within roughly its configured window", elapsed < spec.startup_timeout_seconds + 5.0)
        state = read_state("dummy_hung", tmp)
        check("a timed-out start persists a FAILED record rather than vanishing silently", state is not None and state.get("phase") == "failed")
        check("the actual spawned process is terminated, not abandoned as an orphan", state is not None and not is_pid_alive(state["pid"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─── B: safety — never signal a pid that doesn't look like ours ────────

def test_refuses_to_stop_mismatched_pid():
    # A fully separate dummy process, NOT started via SAMRuntime.start().
    # We deliberately mislabel its pid as belonging to "dummy_api" (whose
    # cmdline_fragment is "health_server.py", which this process's real
    # command line does not contain) to prove stop() refuses to signal a
    # pid that doesn't match, rather than trusting the state file blindly.
    # If this ever fails, stop() would be signaling processes it has no
    # business touching — exactly what Section 7 warns against.
    bystander = subprocess.Popen([sys.executable, str(SLEEPER)], cwd=str(FIXTURE_DIR))
    tmp = None
    try:
        time.sleep(0.3)
        spec = http_spec("dummy_api", free_port())
        rt, tmp = new_runtime([spec])
        write_state("dummy_api", bystander.pid, spec.command, tmp)

        result = rt.stop("dummy_api")
        check("stop() refuses a pid whose cmdline doesn't match what we expect", not result.ok)
        check("the mismatched bystander process is left completely untouched", is_pid_alive(bystander.pid))
    finally:
        bystander.terminate()
        bystander.wait(timeout=5)
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def test_stale_state_is_recovered():
    rt, tmp = new_runtime([sleeper_spec()])
    try:
        write_state("dummy_sleep", 999_999, [sys.executable, str(SLEEPER)], tmp)  # essentially guaranteed dead
        result = rt.stop("dummy_sleep")
        check("stop() recognizes a dead pid from stale state and clears it", result.ok and result.already_stopped)
        check("stale state is actually removed from disk", read_state("dummy_sleep", tmp) is None)

        start_result = rt.start("dummy_sleep")
        check("start() works normally after stale state was cleared", start_result.ok)
        rt.stop("dummy_sleep")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─── C: restart, and multiple independent processes ────────────────────

def test_restart_gets_a_new_pid():
    rt, tmp = new_runtime([sleeper_spec()])
    try:
        first = rt.start("dummy_sleep")
        restart_result = rt.restart("dummy_sleep")
        check("restart() reports success", restart_result.ok)
        check("restart() actually stopped the old process", not is_pid_alive(first.pid))
        new_pid = restart_result.start_result.pid if restart_result.start_result else None
        check("restart() produces a new, different, live pid", new_pid is not None and new_pid != first.pid and is_pid_alive(new_pid))
        rt.stop("dummy_sleep")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_multiple_processes_are_independent():
    voice = sleeper_spec(name="voice", fragment="sleeper.py")
    api = http_spec("api", free_port())
    rt, tmp = new_runtime([voice, api])
    try:
        started = rt.start_all()
        check("start_all() starts every configured process", all(r.ok for r in started.values()))
        check("start_all() gives each process its own state file", read_state("voice", tmp) is not None and read_state("api", tmp) is not None)

        stop_one = rt.stop("voice")
        check("stopping one process succeeds", stop_one.ok)
        check("stopping one process leaves the other running", rt.is_running("api"))

        rt.stop_all()
        check("stop_all() leaves nothing running", not rt.is_running("voice") and not rt.is_running("api"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_unknown_process_name_raises():
    rt, tmp = new_runtime([sleeper_spec()])
    try:
        raised = False
        try:
            rt.start("not_a_real_process")
        except ValueError:
            raised = True
        check("start() raises a clear error for an unregistered process name", raised)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("=== A: start / stop / idempotency ===")
    test_start_and_stop_alive_after_grace()
    test_start_failure_is_explicit()
    test_http_ready_check_success()
    test_http_ready_check_timeout_cleans_up()

    print("\n=== B: safety — pid-mismatch and stale-state handling ===")
    test_refuses_to_stop_mismatched_pid()
    test_stale_state_is_recovered()

    print("\n=== C: restart and multi-process independence ===")
    test_restart_gets_a_new_pid()
    test_multiple_processes_are_independent()
    test_unknown_process_name_raises()

    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("All runtime.lifecycle offline checks passed.")
    print(
        "NOTE: exercises SAMRuntime against throwaway dummy scripts only. "
        "Never spawns or signals the real main.py, interfaces.api.server, or "
        "interfaces.telegram.telegram_bridge, and never touches ~/.sam_data. "
        "Real-process behavior (actual Ollama health, actual Telegram "
        "polling, actual voice pipeline) is UNVERIFIED by this suite."
    )


if __name__ == "__main__":
    main()
