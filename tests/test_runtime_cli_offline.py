"""
OFFLINE CLI integration test suite — Phase 3B, Checkpoint 5.

Two things this covers, for two different reasons:

1. EVERY dispatchable sam_cli.py subcommand actually runs without an
   uncaught NameError/AttributeError. This is a direct regression guard
   against the exact bug Checkpoint 5 found: `cmd_skills` was referenced
   by a subparser and the commands dispatch dict but was never defined
   anywhere, which crashed every single command (not just "skills")
   because the dict is built unconditionally before dispatch runs.
   sam_cli.py had no test coverage at all before this file — that's
   exactly how that bug went unnoticed since the initial commit.

2. cmd_start/cmd_stop/cmd_restart correctly delegate to runtime.SAMRuntime
   and print sensible output for success/failure/already-running cases,
   using a fake runtime double. The real SAMRuntime is already covered by
   test_runtime_lifecycle_offline.py and test_runtime_health_offline.py,
   and was additionally verified manually against the real
   interfaces.api.server during Checkpoint 5 (real start, real graceful
   stop confirming the Checkpoint 3 shutdown-wiring fix live, real
   restart across separate process invocations with a genuinely different
   pid). This suite does not re-prove SAMRuntime works — it proves
   sam_cli.py calls it correctly.

Every subprocess invocation here gets its own throwaway HOME so
~/.sam_data is never touched — except `start api`/`stop api`/`restart
api`, which deliberately share ONE home with each other (but still never
touch the real ~/.sam_data): those three are real subprocesses that
really spawn/manage a real interfaces.api.server, and stop/restart need
the same state file start wrote in order to actually find and manage it.
This was fixed after discovering the previous per-invocation-isolated
version left that real process running, unmanaged, after every run of
this suite — see test_every_command_survives_dispatch's own comment for
the full explanation. "no"/cancel is piped to any command that might
prompt for confirmation, so nothing destructive ever actually runs.

Usage:
    python3 tests/test_runtime_cli_offline.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))
REPO_ROOT = Path(__file__).parent.parent

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(bool(condition))
    print(f"[{status}] {label}")


def run_cli(args, input_text="no\n", timeout=15, home=None):
    owns_home = home is None
    if home is None:
        home = Path(tempfile.mkdtemp(prefix="sam_cli_test_home_"))
    try:
        return subprocess.run(
            [sys.executable, "sam_cli.py"] + args,
            cwd=str(REPO_ROOT),
            env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    finally:
        if owns_home:
            shutil.rmtree(home, ignore_errors=True)


UNCAUGHT_ERRORS = ("NameError", "AttributeError", "ImportError", "ModuleNotFoundError")


def _no_uncaught_python_error(proc: subprocess.CompletedProcess) -> bool:
    return not any(err in proc.stderr for err in UNCAUGHT_ERRORS)


# ─── A: every dispatchable command runs without an uncaught error ──────

# (argv-after-command, description) — dummy args only where argparse
# requires them; the goal is reaching and surviving dispatch, not
# necessarily succeeding at the underlying operation.
COMMAND_INVOCATIONS = [
    (["status"], "status"),
    (["doctor"], "doctor"),
    (["start", "api"], "start api"),
    (["stop", "api"], "stop api"),
    (["restart", "api"], "restart api"),
    (["skills"], "skills (the bug this checkpoint found and fixed)"),
    (["founder"], "founder"),
    (["founder-review"], "founder-review"),
    (["devices"], "devices"),
    (["revoke-device", "999"], "revoke-device"),
    (["export"], "export"),
    (["export-profile"], "export-profile"),
    (["sync-status"], "sync-status"),
    (["reset-memory"], "reset-memory (input='no' — must not actually wipe anything)"),
    (["reset-all"], "reset-all (input='no' — must not actually wipe anything)"),
    (["license"], "license"),
    (["activate", "/nonexistent/file.lic"], "activate"),
    (["logs"], "logs"),
    (["memory"], "memory"),
    (["decision", "d", "r"], "decision"),
    (["rejection", "w", "y"], "rejection"),
    (["import-profile", "/nonexistent/file.zip"], "import-profile"),
]


def test_every_command_survives_dispatch():
    # start/stop/restart api are the three exceptions to "every invocation
    # gets its own disconnected home" above them: each is a REAL
    # subprocess (mock.patch in *this* process can't reach a separate
    # child interpreter), so `sam_cli.py start api` really spawns a real
    # interfaces.api.server. Giving stop/restart their own fresh,
    # disconnected home — like every other command in this loop — means
    # they'd have no state file to find that real process by, so it would
    # never actually be stopped. Confirmed empirically (not hypothetical):
    # this suite genuinely leaked a real, unmanaged interfaces.api.server
    # process into the environment on every run before this fix, because
    # `stop api` was checking a completely different, empty ~/.sam_data.
    api_lifecycle_home = Path(tempfile.mkdtemp(prefix="sam_cli_test_home_api_lifecycle_"))
    try:
        for argv, desc in COMMAND_INVOCATIONS:
            shared = argv[:2] in (["start", "api"], ["stop", "api"], ["restart", "api"])
            try:
                proc = run_cli(argv, home=api_lifecycle_home if shared else None)
                check(f"'{desc}' runs without an uncaught Python error", _no_uncaught_python_error(proc))
            except subprocess.TimeoutExpired:
                check(f"'{desc}' runs without an uncaught Python error", False)
    finally:
        # Defense-in-depth, not a substitute for `stop api` above actually
        # working: this suite should now never leak, but guarantees it
        # structurally rather than relying solely on the stop call above.
        _ensure_stopped(api_lifecycle_home, "api")
        shutil.rmtree(api_lifecycle_home, ignore_errors=True)


def _ensure_stopped(home: Path, process_name: str):
    """Defense-in-depth safety net only — not a substitute for the `stop
    api` call in the loop above actually working (it does; this
    guarantees it structurally, independent of relying on that call
    succeeding). Delegates to the real SAMRuntime.stop() rather than a
    bare os.kill(SIGTERM): stop() polls for actual death and escalates to
    SIGKILL after spec.shutdown_timeout_seconds if needed. A bare SIGTERM
    is not equivalent — confirmed empirically, interfaces.api.server does
    not exit within 1s of SIGTERM alone, so a fire-and-forget signal with
    no wait is not a real safety net, just a false sense of one."""
    from runtime.lifecycle.manager import SAMRuntime
    SAMRuntime(data_dir=home / ".sam_data").stop(process_name)


def test_reset_commands_did_not_actually_reset():
    # Belt-and-suspenders: confirm piping "no" really was a no-op, since
    # test_every_command_survives_dispatch's HOME is thrown away anyway —
    # this checks the *behavior*, not just the absence of a crash, against
    # a HOME we inspect afterward.
    home = Path(tempfile.mkdtemp(prefix="sam_cli_test_reset_"))
    try:
        sam_data = home / ".sam_data"
        sam_data.mkdir()
        (sam_data / "identity.json").write_text('{"name": "test"}')
        subprocess.run(
            [sys.executable, "sam_cli.py", "reset-all"],
            cwd=str(REPO_ROOT), env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
            input="no\n", capture_output=True, text=True, timeout=10,
        )
        check("declining reset-all's confirmation leaves ~/.sam_data untouched", (sam_data / "identity.json").exists())
    finally:
        shutil.rmtree(home, ignore_errors=True)


# ─── B: cmd_start/cmd_stop/cmd_restart delegate correctly ──────────────

class FakeResult:
    def __init__(self, name, ok, pid=None, message="", already_running=False, already_stopped=False):
        self.name, self.ok, self.pid, self.message = name, ok, pid, message
        self.already_running, self.already_stopped = already_running, already_stopped


class FakeRestartResult:
    def __init__(self, name, start_result=None, message=""):
        self.name, self.start_result, self.message = name, start_result, message


class FakeRuntime:
    process_names = ["voice", "api", "telegram"]

    def __init__(self, *a, **kw):
        pass

    def start(self, name):
        return FakeResult(name, ok=True, pid=1234, message=f"{name} is ready (pid 1234).")

    def stop(self, name):
        return FakeResult(name, ok=True, message=f"{name} stopped gracefully.")

    def restart(self, name):
        return FakeRestartResult(name, start_result=FakeResult(name, ok=True, pid=5678, message=f"{name} is ready (pid 5678)."))

    def start_all(self):
        return {n: self.start(n) for n in self.process_names}

    def stop_all(self):
        return {n: self.stop(n) for n in self.process_names}


class FakeRuntimeAlreadyRunning(FakeRuntime):
    def start(self, name):
        return FakeResult(name, ok=True, pid=1234, already_running=True)


class FakeRuntimeFailure(FakeRuntime):
    def start(self, name):
        return FakeResult(name, ok=False, message=f"{name} exited during startup (code 1).")


def test_cmd_start_single_process(capsys=None):
    import sam_cli
    with mock.patch("runtime.SAMRuntime", FakeRuntime):
        sam_cli.cmd_start("api")


def _capture_stdout(fn, *a, **kw):
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


def test_cmd_start_stop_restart_output():
    import sam_cli

    with mock.patch("runtime.SAMRuntime", FakeRuntime):
        out = _capture_stdout(sam_cli.cmd_start, "api")
        check("cmd_start(name) prints success for a single process", "api" in out and "✅" in out)

        out = _capture_stdout(sam_cli.cmd_start, None)
        check("cmd_start(None) starts all three processes", all(n in out for n in ("voice", "api", "telegram")))

        out = _capture_stdout(sam_cli.cmd_stop, "api")
        check("cmd_stop(name) prints success", "✅" in out)

        out = _capture_stdout(sam_cli.cmd_restart, "api")
        check("cmd_restart(name) prints the post-restart result", "5678" in out or "✅" in out)

    with mock.patch("runtime.SAMRuntime", FakeRuntimeAlreadyRunning):
        out = _capture_stdout(sam_cli.cmd_start, "api")
        check("cmd_start reports already-running distinctly, not as a fresh success", "already running" in out)

    with mock.patch("runtime.SAMRuntime", FakeRuntimeFailure):
        out = _capture_stdout(sam_cli.cmd_start, "api")
        check("cmd_start surfaces a failure message rather than printing success", "❌" in out and "exited during startup" in out)


def test_cmd_doctor_smoke():
    import sam_cli
    out = _capture_stdout(sam_cli.cmd_doctor)
    check("cmd_doctor() runs without crashing and prints a summary line", "checks)" in out)
    check("cmd_doctor() reports at least one check", any(word in out for word in ("PASS", "WARN", "FAIL", "UNVERIFIED")))


def main():
    print("=== A: every dispatchable command survives dispatch ===")
    test_every_command_survives_dispatch()
    test_reset_commands_did_not_actually_reset()

    print("\n=== B: cmd_start/cmd_stop/cmd_restart delegate correctly ===")
    test_cmd_start_stop_restart_output()
    test_cmd_doctor_smoke()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("All CLI integration offline checks passed.")
    print(
        "NOTE: part A runs the real sam_cli.py as a subprocess for every "
        "command with an isolated HOME; part B uses a fake runtime double "
        "and never touches a real process. The real SAMRuntime lifecycle is "
        "covered by test_runtime_lifecycle_offline.py and "
        "test_runtime_health_offline.py, and was verified manually against "
        "the real interfaces.api.server during Checkpoint 5 itself."
    )


if __name__ == "__main__":
    main()
