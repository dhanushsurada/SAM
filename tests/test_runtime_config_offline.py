"""
OFFLINE config-centralization test suite — Phase 3B follow-up.

RUNTIME.md Section 6 flagged this gap explicitly: interfaces/api/server.py
hardcoded host/port, runtime/lifecycle/specs.py held an independent literal
copy of the port for its health_url, and sam_cli.py's `doctor` port-free
check held a third independent copy. Three literals that happened to agree
is not centralization — it's three places that could silently drift apart.

This suite proves config.settings.Settings is now the one actual source:
  A) defaults still match the historical hardcoded values (regression safety)
  B) overriding Settings changes specs.py's health_url, not just Settings itself
  C) overriding Settings changes what server.py's main() actually binds to
  D) overriding Settings changes what `sam doctor` actually checks/reports

Every check spawns a fresh subprocess under its own isolated HOME rather
than mutating os.environ mid-process. This is deliberate, not stylistic:
config.settings.SAM_DATA_DIR is computed once at first import of that
module (Path.home() / ".sam_data"), so changing HOME after something in
the current process has already imported config.settings would silently
have no effect and produce a false pass. A fresh subprocess is the only
way to guarantee a clean first import under the HOME being tested.

Never touches ~/.sam_data. Never binds a real port (uvicorn.run is mocked
in section C; section D only asks whether a port is free, which is what
sam_cli.py already did before this change too). A real end-to-end check —
actually binding interfaces.api.server on a non-default port and polling
it live — is deliberately NOT here; it's a real-process check, documented
separately, same as the rest of this codebase's REAL-PROCESS TESTED items.

Usage:
    python3 tests/test_runtime_config_offline.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
REPO_ROOT = Path(__file__).parent.parent

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(bool(condition))
    print(f"[{status}] {label}")


def _isolated_home(overrides_yaml: str = "") -> Path:
    home = Path(tempfile.mkdtemp(prefix="sam_config_test_home_"))
    if overrides_yaml:
        data_dir = home / ".sam_data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "settings.yaml").write_text(overrides_yaml)
    return home


def _run_py(script: str, home: Path, timeout=15) -> str:
    """Run `script` as a fresh interpreter under `home` as HOME, return stdout."""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout, result.stderr


def _settings_and_specs_snapshot(home: Path) -> dict:
    script = (
        f"import sys, json; sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from config.settings import Settings\n"
        "from runtime.lifecycle.specs import default_specs\n"
        "s = Settings()\n"
        f"specs = {{sp.name: sp for sp in default_specs({str(REPO_ROOT)!r})}}\n"
        "print(json.dumps({'api_host': s.api_host, 'api_port': s.api_port, "
        "'health_url': specs['api'].health_url}))\n"
    )
    out, err = _run_py(script, home)
    try:
        return json.loads(out.strip().splitlines()[-1])
    except Exception:
        raise AssertionError(f"snapshot subprocess produced no JSON.\nstdout={out!r}\nstderr={err!r}")


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


# ─── A: defaults match the historical hardcoded values ──────────────────

def test_defaults_match_prior_hardcoded_values():
    home = _isolated_home()
    try:
        snap = _settings_and_specs_snapshot(home)
        check("Settings().api_host defaults to 0.0.0.0 (matches the old hardcoded value)", snap["api_host"] == "0.0.0.0")
        check("Settings().api_port defaults to 8420 (matches the old hardcoded value)", snap["api_port"] == 8420)
        check("default_specs()'s api health_url still targets the default port", snap["health_url"] == "http://127.0.0.1:8420/api/iqoo/health")
    finally:
        shutil.rmtree(home, ignore_errors=True)


# ─── B: overriding Settings changes specs.py's health_url ───────────────

def test_override_reaches_specs_health_url():
    home = _isolated_home("api_host: '127.0.0.1'\napi_port: 54321\n")
    try:
        snap = _settings_and_specs_snapshot(home)
        check("Settings().api_port reflects the ~/.sam_data/settings.yaml override", snap["api_port"] == 54321)
        check("default_specs()'s api health_url uses the SAME overridden port", "54321" in snap["health_url"])
        check("default_specs()'s api health_url does not fall back to the old literal 8420", "8420" not in snap["health_url"])
    finally:
        shutil.rmtree(home, ignore_errors=True)


# ─── C: overriding Settings changes what server.py actually binds ───────

def test_override_reaches_server_main():
    home = _isolated_home("api_host: '127.0.0.7'\napi_port: 54322\n")
    try:
        script = (
            f"import sys, json; sys.path.insert(0, {str(REPO_ROOT)!r})\n"
            "from unittest.mock import patch\n"
            "import interfaces.api.server as server_module\n"
            "with patch('uvicorn.run') as mock_run:\n"
            "    server_module.main()\n"
            "_, kwargs = mock_run.call_args\n"
            "print(json.dumps({'host': kwargs.get('host'), 'port': kwargs.get('port')}))\n"
        )
        out, err = _run_py(script, home)
        result = json.loads(out.strip().splitlines()[-1])
        check("server.main() calls uvicorn.run with Settings().api_host, not a literal", result["host"] == "127.0.0.7")
        check("server.main() calls uvicorn.run with Settings().api_port, not a literal", result["port"] == 54322)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_iqoo_server_shim_inherits_the_same_fix():
    # iqoo/server.py does `from interfaces.api.server import app, main` — no
    # separate implementation. Confirms that's still true after this change
    # (the shim can't quietly drift into its own copy of the wiring).
    home = _isolated_home()
    try:
        script = (
            f"import sys; sys.path.insert(0, {str(REPO_ROOT)!r})\n"
            "import iqoo.server as shim\n"
            "import interfaces.api.server as canonical\n"
            "print('SAME' if shim.main is canonical.main else 'DIFFERENT')\n"
        )
        out, _ = _run_py(script, home)
        check("iqoo.server.main is still identically interfaces.api.server.main (shim, not a fork)", out.strip().splitlines()[-1] == "SAME")
    finally:
        shutil.rmtree(home, ignore_errors=True)


# ─── D: overriding Settings changes what `sam doctor` reports ───────────

def test_doctor_reports_default_port():
    home = _isolated_home()
    try:
        result = run_cli(["doctor"], home)
        check("`sam doctor` exits cleanly with default settings", result.returncode in (0, 1))  # 1 = some WARN/FAIL rows (e.g. Ollama unreachable), not a crash
        check("`sam doctor` mentions the default port 8420 with no override present", "8420" in result.stdout)
        for err in ("NameError", "AttributeError: module 'sam_cli'"):
            check(f"`sam doctor` output has no uncaught {err}", err not in result.stdout and err not in result.stderr)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_doctor_reports_overridden_port():
    home = _isolated_home("api_port: 54323\n")
    try:
        result = run_cli(["doctor"], home)
        check("`sam doctor` exits cleanly with an overridden port", result.returncode in (0, 1))
        check("`sam doctor` reports the OVERRIDDEN port 54323, not the old literal", "54323" in result.stdout)
        check("`sam doctor` no longer prints the old hardcoded 8420 when overridden", "8420" not in result.stdout)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def main():
    print("=== A: defaults match the historical hardcoded values ===")
    test_defaults_match_prior_hardcoded_values()

    print("\n=== B: override reaches runtime/lifecycle/specs.py ===")
    test_override_reaches_specs_health_url()

    print("\n=== C: override reaches interfaces/api/server.py ===")
    test_override_reaches_server_main()
    test_iqoo_server_shim_inherits_the_same_fix()

    print("\n=== D: override reaches sam_cli.py doctor ===")
    test_doctor_reports_default_port()
    test_doctor_reports_overridden_port()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("All runtime-config offline checks passed.")
    print(
        "NOTE: proves Settings is the single source of truth via subprocess "
        "snapshots and a mocked uvicorn.run — never binds a real port. A real "
        "process bound to a non-default port, polled live via `sam status`, "
        "is a separate REAL-PROCESS check, not part of this offline suite."
    )


if __name__ == "__main__":
    main()
