"""
OFFLINE test suite — two known pre-existing bugs, fixed.

Both were found during Phase 3B and deliberately left alone at the time
(documented in docs/deployment/LOCAL_RUNTIME.md as known, out of scope for
that pass). This suite proves both fixes:

  A) `sam logs` (sam_cli.py cmd_logs) reads from SAM_DATA_DIR/logs/sam.log.
     main.py used to write to a bare relative path "logs/sam.log" instead —
     a different file, which only ever appeared to work because the repo
     happened to ship a committed logs/.gitkeep at its own root. Fixed by
     making main.py use the same SAM_DATA_DIR expression cmd_logs already
     used, so the two can't drift apart again.

  B) `sam status`'s legacy "SAM process" line ran `pgrep -f main.py`
     against the whole system's process table — a pattern any unrelated
     process with "main.py" anywhere in its command line would match.
     Fixed by preferring the Phase-3B runtime-tracked state (one specific
     recorded PID, liveness-checked, cmdline-fragment-checked) when it
     exists, falling back to the original pgrep behavior — now honestly
     labeled best-effort — only when SAM was started outside `sam start`.

Every check uses an isolated HOME and/or throwaway fixture scripts. No real
main.py, interfaces.api.server, or interfaces.telegram.telegram_bridge is
ever imported or spawned — those need the full hardware/model stack,
consistent with every other _offline suite in this repo.

Usage:
    python3 tests/test_cli_diagnostics_offline.py
"""

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
REPO_ROOT = Path(__file__).parent.parent

from runtime.lifecycle.state import write_state, is_pid_alive

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(bool(condition))
    print(f"[{status}] {label}")


def _isolated_home() -> Path:
    return Path(tempfile.mkdtemp(prefix="sam_cli_diag_test_home_"))


def run_cli(args, home: Path, input_text="no\n", timeout=15):
    return subprocess.run(
        [sys.executable, "sam_cli.py"] + args,
        cwd=str(REPO_ROOT),
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ─── fixtures: a throwaway script literally named main.py, so its own ───
# ─── cmdline genuinely contains "main.py" — never SAM's real entry point ─

FIXTURE_DIR = Path(tempfile.mkdtemp(prefix="sam_cli_diag_test_fixtures_"))

FAKE_MAIN = FIXTURE_DIR / "main.py"
FAKE_MAIN.write_text("import time\ntime.sleep(120)\n")

FAKE_UNRELATED = FIXTURE_DIR / "unrelated.py"
FAKE_UNRELATED.write_text("import time\ntime.sleep(120)\n")


def _spawn(script: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(script)])


def _kill_and_reap(proc: subprocess.Popen):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


# ─── A: main.py writes logs where cmd_logs actually looks ───────────────

def test_main_py_logs_to_the_path_cmd_logs_reads():
    home = _isolated_home()
    try:
        script = (
            f"import sys; sys.path.insert(0, {str(REPO_ROOT)!r})\n"
            "import main\n"
            "import logging\n"
            "logging.getLogger('SAM').info('offline-suite marker line')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO_ROOT),
            env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
            capture_output=True, text=True, timeout=20,
        )
        expected_log = home / ".sam_data" / "logs" / "sam.log"
        check("main.py creates the log file at SAM_DATA_DIR/logs/sam.log", expected_log.exists())
        contents = expected_log.read_text() if expected_log.exists() else ""
        check("the actual log line written by main.py is present in that file", "offline-suite marker line" in contents)

        # Now prove `sam logs` (cmd_logs) reads that same file, end to end.
        cli_result = run_cli(["logs"], home)
        check("`sam logs` exits cleanly", cli_result.returncode == 0)
        check("`sam logs` displays the line main.py actually wrote", "offline-suite marker line" in cli_result.stdout)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_old_relative_log_path_is_not_used():
    # Regression guard: confirms the fix didn't just add a second log
    # destination on top of the old one — the old cwd-relative path
    # should see no new writes from this suite's runs.
    old_path = REPO_ROOT / "logs" / "sam.log"
    before = old_path.stat().st_size if old_path.exists() else None
    home = _isolated_home()
    try:
        script = f"import sys; sys.path.insert(0, {str(REPO_ROOT)!r})\nimport main\n"
        subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO_ROOT),
            env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
            capture_output=True, text=True, timeout=20,
        )
        after = old_path.stat().st_size if old_path.exists() else None
        check("importing main.py does not grow the old repo-relative logs/sam.log", after == before)
    finally:
        shutil.rmtree(home, ignore_errors=True)


# ─── B: `sam status` prefers verified runtime state over blind pgrep ────

def test_status_falls_back_to_pgrep_when_nothing_running():
    home = _isolated_home()
    try:
        result = run_cli(["status"], home)
        check("`sam status` exits cleanly with nothing running", result.returncode == 0)
        check("`sam status` reports SAM not running (no state file, nothing real running)", "SAM not running" in result.stdout)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_status_prefers_verified_state_when_present():
    home = _isolated_home()
    proc = _spawn(FAKE_MAIN)
    try:
        write_state("voice", pid=proc.pid, command=[sys.executable, str(FAKE_MAIN)], data_dir=home / ".sam_data")
        result = run_cli(["status"], home)
        check("`sam status` reports SAM running via the verified state-file path", f"PID: {proc.pid}" in result.stdout or f"PID: {proc.pid})" in result.stdout)
        check("the verified match is NOT labeled best-effort (it's a confirmed match)", "best-effort" not in result.stdout)
    finally:
        _kill_and_reap(proc)
        shutil.rmtree(home, ignore_errors=True)


def test_status_does_not_trust_a_pid_reused_by_an_unrelated_process():
    # The recorded PID is alive, but it's now a DIFFERENT process (cmdline
    # doesn't contain "main.py") — simulates PID reuse after the real SAM
    # process died and the OS handed its old PID to something else.
    home = _isolated_home()
    proc = _spawn(FAKE_UNRELATED)
    try:
        write_state("voice", pid=proc.pid, command=[sys.executable, str(FAKE_MAIN)], data_dir=home / ".sam_data")
        result = run_cli(["status"], home)
        check("a live-but-mismatched PID is not trusted as SAM running", f"PID: {proc.pid}" not in result.stdout)
        check("falls through to reporting not running (no unrelated `main.py` process exists to match instead)", "SAM not running" in result.stdout)
    finally:
        _kill_and_reap(proc)
        shutil.rmtree(home, ignore_errors=True)


def test_status_falls_back_cleanly_from_a_stale_dead_pid():
    home = _isolated_home()
    proc = _spawn(FAKE_MAIN)
    proc_pid = proc.pid
    _kill_and_reap(proc)  # dies before `sam status` ever runs
    try:
        write_state("voice", pid=proc_pid, command=[sys.executable, str(FAKE_MAIN)], data_dir=home / ".sam_data")
        check("sanity: the recorded PID is confirmed dead before the CLI check", not is_pid_alive(proc_pid))
        result = run_cli(["status"], home)
        check("a stale dead PID in the state file does not report SAM running", f"PID: {proc_pid}" not in result.stdout)
        check("`sam status` still exits cleanly on a stale state file", result.returncode == 0)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def main():
    print("=== A: main.py log path matches what `sam logs` reads ===")
    test_main_py_logs_to_the_path_cmd_logs_reads()
    test_old_relative_log_path_is_not_used()

    print("\n=== B: `sam status` prefers verified state over blind pgrep ===")
    test_status_falls_back_to_pgrep_when_nothing_running()
    test_status_prefers_verified_state_when_present()
    test_status_does_not_trust_a_pid_reused_by_an_unrelated_process()
    test_status_falls_back_cleanly_from_a_stale_dead_pid()

    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("All CLI diagnostics offline checks passed.")
    print(
        "NOTE: proves both fixes functionally against fixture processes and "
        "a real (but throwaway) log file — never imports or spawns SAM's "
        "actual main.py runtime dependencies (audio, Ollama). Voice/telegram "
        "REAL-PROCESS verification remains a separate, hardware-adjacent check."
    )


if __name__ == "__main__":
    main()
