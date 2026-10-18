"""
OFFLINE test suite for Phase C1-C3 — the JSON runtime bridge, OllamaManager,
and ModelManager.pull()'s failure path. Deterministic without a real Ollama
or the API process's dependencies (fastapi/uvicorn) installed: every check
here asserts behavior that holds whether or not Ollama/fastapi happen to be
present in the environment running the suite.

Usage:
    python3 tests/test_runtime_bridge_offline.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
REPO_ROOT = Path(__file__).parent.parent

from runtime.health.status import RuntimeStatus
from runtime.ollama.manager import OllamaManager
from runtime.setup_state import read_setup_state, write_setup_state
from config.settings import Settings
from core.model_manager import ModelManager, OllamaUnavailableError

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(bool(condition))
    print(f"[{status}] {label}")


def _isolated_home() -> Path:
    home = Path(tempfile.mkdtemp(prefix="sam_bridge_test_home_"))
    (home / ".sam_data").mkdir()
    return home


def _run_cli(args: list[str], home: Path):
    env = {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "PYTHONPATH": ":".join(sys.path),
    }
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "sam_cli.py"), *args],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=env, timeout=30,
    )


# ─── A: RuntimeStatus extension ────────────────────────────────────────────

def test_not_installed_added_without_disturbing_existing_members():
    original = {"STOPPED", "STARTING", "READY", "DEGRADED", "FAILED", "STOPPING"}
    actual = {m.name for m in RuntimeStatus}
    check("all 6 pre-Phase-C members are still present", original.issubset(actual))
    check("NOT_INSTALLED was added", "NOT_INSTALLED" in actual)
    check("NOT_INSTALLED is a real str value, not a placeholder",
          RuntimeStatus.NOT_INSTALLED.value == "NOT_INSTALLED")


# ─── B: sam_cli.py --json mode ─────────────────────────────────────────────

def test_status_json_is_valid_and_well_shaped():
    home = _isolated_home()
    try:
        r = _run_cli(["status", "--json"], home)
        check("status --json exits (doesn't hang/crash)", r.returncode in (0, 1))
        try:
            payload = json.loads(r.stdout.strip())
            parsed = True
        except ValueError:
            parsed, payload = False, {}
        check("stdout is valid JSON", parsed)
        check("has 'success' key", "success" in payload)
        check("has 'ollama' key with a 'state'", "state" in payload.get("ollama", {}))
        check("has 'processes' key covering voice/api/telegram",
              set(payload.get("processes", {}).keys()) == {"voice", "api", "telegram"})
        check("reported ollama state is a real RuntimeStatus value",
              payload.get("ollama", {}).get("state") in [m.value for m in RuntimeStatus])
        check("no ANSI escape codes in JSON output", "\x1b[" not in r.stdout)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_status_human_mode_is_unchanged_and_not_json():
    home = _isolated_home()
    try:
        r = _run_cli(["status"], home)
        check("plain `status` still exits 0", r.returncode == 0)
        check("plain `status` prints the human banner", "SAM STATUS" in r.stdout)
        try:
            json.loads(r.stdout.strip())
            is_json = True
        except ValueError:
            is_json = False
        check("plain `status` output is NOT JSON (modes stay distinct)", not is_json)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_doctor_json_has_structured_checks():
    home = _isolated_home()
    try:
        r = _run_cli(["doctor", "--json"], home)
        payload = json.loads(r.stdout.strip())
        check("doctor --json has a 'checks' list", isinstance(payload.get("checks"), list))
        check("doctor --json has at least as many checks as the human mode's own count",
              len(payload["checks"]) >= 15)
        check("every check has label/status/detail keys",
              all({"label", "status", "detail"} <= set(c.keys()) for c in payload["checks"]))
        check("every check's status is one of the four known values",
              all(c["status"] in ("PASS", "WARN", "FAIL", "UNVERIFIED") for c in payload["checks"]))
        check("summary counts match the checks list",
              payload["summary"]["total"] == len(payload["checks"]))
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_stop_json_is_safe_and_deterministic_regardless_of_environment():
    """Doesn't try to start anything (that's environment-dependent — needs
    fastapi/uvicorn for `api`). Stopping an already-stopped process is
    deterministic everywhere and exercises the same JSON serialization
    path start/restart share."""
    home = _isolated_home()
    try:
        r = _run_cli(["stop", "api", "--json"], home)
        payload = json.loads(r.stdout.strip())
        check("stop --json succeeds", payload.get("success") is True)
        check("reports already_stopped for a process that was never running",
              payload["results"]["api"]["already_stopped"] is True)
        check("dataclass serialization preserved the 'name' field", payload["results"]["api"]["name"] == "api")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_ollama_cli_subcommand_json_matches_manager_directly():
    """Phase C4 addition: `sam_cli.py ollama status --json` is a thin
    subprocess-invokable wrapper around the exact same OllamaManager the
    direct-import tests below exercise -- asserting that, not just that
    the subcommand runs."""
    home = _isolated_home()
    try:
        r = _run_cli(["ollama", "status", "--json"], home)
        payload = json.loads(r.stdout.strip())
        direct = OllamaManager().status()
        check("CLI `ollama status --json` reports the same state OllamaManager().status() does",
              payload["state"] == direct["state"])
        check("exit code reflects READY vs not", (r.returncode == 0) == (payload["state"] == "READY"))
    finally:
        shutil.rmtree(home, ignore_errors=True)


# ─── C: OllamaManager ───────────────────────────────────────────────────────

def test_ollama_manager_status_is_one_of_the_three_relevant_states():
    status = OllamaManager().status()
    check("status() returns a dict with 'state'", "state" in status)
    check("state is READY, STOPPED, or NOT_INSTALLED",
          status["state"] in (RuntimeStatus.READY.value, RuntimeStatus.STOPPED.value,
                               RuntimeStatus.NOT_INSTALLED.value))
    check("models is always a list, even when empty", isinstance(status.get("models"), list))


def test_ollama_manager_start_never_lies_about_success():
    result = OllamaManager().start(timeout_s=1)
    check("start() returns ok/already_running/message keys",
          {"ok", "already_running", "message"} <= set(result.keys()))
    if not result["ok"]:
        check("a failed start() explains why in message", len(result["message"]) > 0)


def test_ollama_manager_has_no_stop_method():
    """Phase B/C2 decision: SAM must not be able to kill a process it may
    not own. Asserting the method doesn't exist, not just that it's
    unused, so this fails loudly if a future edit adds one."""
    check("OllamaManager exposes no stop()", not hasattr(OllamaManager, "stop"))


# ─── D: ModelManager.pull() ─────────────────────────────────────────────────

def test_pull_raises_ollama_unavailable_when_unreachable():
    settings = Settings()
    settings.ollama_host = "http://127.0.0.1:1"  # a port nothing listens on
    mm = ModelManager(settings)
    raised = False
    try:
        next(mm.pull("qwen2.5:14b"))
    except OllamaUnavailableError:
        raised = True
    except Exception:
        raised = False
    check("pull() raises OllamaUnavailableError, not a bare/uncaught exception, when unreachable", raised)


def test_pull_is_a_generator_not_a_list():
    """It must not eagerly connect at call time — only on first next() —
    so a caller can build the SSE response object before any network
    activity starts (matches how the endpoint in server.py uses it)."""
    settings = Settings()
    settings.ollama_host = "http://127.0.0.1:1"
    mm = ModelManager(settings)
    gen = mm.pull("qwen2.5:14b")
    check("pull() returns immediately without raising (lazy)", gen is not None)
    check("pull() is a generator", hasattr(gen, "__next__"))


# ─── E: SetupState (Phase C7) ───────────────────────────────────────────────

def test_setup_state_defaults_to_first_run_when_absent():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "setup_state.json"
        result = read_setup_state(path)
        check("missing file reads as first_run, not an error", result["state"] == "first_run")
        check("selected_model defaults to None", result["selected_model"] is None)


def test_setup_state_round_trips_and_rejects_bad_state():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "setup_state.json"
        write_setup_state("in_progress", path=path)
        check("in_progress round-trips", read_setup_state(path)["state"] == "in_progress")
        write_setup_state("complete", selected_model="qwen2.5:14b", path=path)
        after = read_setup_state(path)
        check("complete + model round-trips", after == {"state": "complete", "selected_model": "qwen2.5:14b"})
        raised = False
        try:
            write_setup_state("not_a_real_state", path=path)
        except ValueError:
            raised = True
        check("an invalid state raises rather than silently writing", raised)


def test_setup_state_corrupt_file_is_treated_as_first_run():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "setup_state.json"
        path.write_text("{not valid json")
        check("corrupt file reads as first_run, not a crash", read_setup_state(path)["state"] == "first_run")


def test_setup_state_cli_round_trip():
    home = _isolated_home()
    try:
        r = _run_cli(["setup-state", "get", "--json"], home)
        check("fresh HOME reads as first_run via the CLI too", json.loads(r.stdout)["state"] == "first_run")

        r = _run_cli(["setup-state", "set", "--state", "complete", "--model", "qwen2.5:14b", "--json"], home)
        payload = json.loads(r.stdout)
        check("CLI set round-trips the model", payload == {"state": "complete", "selected_model": "qwen2.5:14b"})

        r = _run_cli(["setup-state", "get", "--json"], home)
        check("a second CLI process sees the same persisted state", json.loads(r.stdout)["state"] == "complete")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def main():
    print("=== A: RuntimeStatus.NOT_INSTALLED ===")
    test_not_installed_added_without_disturbing_existing_members()

    print("\n=== B: sam_cli.py --json mode ===")
    test_status_json_is_valid_and_well_shaped()
    test_status_human_mode_is_unchanged_and_not_json()
    test_doctor_json_has_structured_checks()
    test_stop_json_is_safe_and_deterministic_regardless_of_environment()

    test_ollama_cli_subcommand_json_matches_manager_directly()

    print("\n=== C: OllamaManager ===")
    test_ollama_manager_status_is_one_of_the_three_relevant_states()
    test_ollama_manager_start_never_lies_about_success()
    test_ollama_manager_has_no_stop_method()

    print("\n=== D: ModelManager.pull() ===")
    test_pull_raises_ollama_unavailable_when_unreachable()
    test_pull_is_a_generator_not_a_list()

    print("\n=== E: SetupState ===")
    test_setup_state_defaults_to_first_run_when_absent()
    test_setup_state_round_trips_and_rejects_bad_state()
    test_setup_state_corrupt_file_is_treated_as_first_run()
    test_setup_state_cli_round_trip()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("All runtime-bridge offline checks passed.")
    print(
        "NOTE: OllamaManager/ModelManager.pull() checks run against whatever "
        "Ollama reachability actually exists in this environment (or doesn't) "
        "-- they assert shape and honest failure-reporting, not a specific "
        "state, so they hold either way. Does not cover: a real pull's "
        "progress stream (needs a real Ollama), POST /api/models/pull "
        "(needs fastapi/uvicorn), or any Tauri/Rust/TypeScript layer."
    )


if __name__ == "__main__":
    main()
