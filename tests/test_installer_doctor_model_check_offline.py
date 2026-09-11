"""
OFFLINE test suite — Phase 4.2, doctor configured-model check.

Exercises the model-presence check added to sam_cli.py's cmd_doctor (Phase
4.1 design item H / audit finding: doctor already confirmed Ollama was
*reachable* and counted how many models were pulled, but never checked
whether the specific configured settings.primary_model was actually among
them — that was only implied by a comment, never enforced).

Uses a real local HTTP server bound to 127.0.0.1 (loopback only, never
touches the real network) standing in for Ollama's /api/tags endpoint, so
cmd_doctor's actual request-handling code path is genuinely exercised end
to end rather than mocked out at the Python level — the same "offline
means loopback, not stubbed" convention already used elsewhere in this
suite (see test_runtime_cli_offline.py's real interfaces.api.server
subprocess).

Each case spawns `python3 sam_cli.py doctor` as a fresh subprocess under
its own isolated HOME with a `~/.sam_data/settings.yaml` pointing
ollama_host at the fake server. This mirrors test_runtime_config_offline.py's
established pattern exactly, for the same reason documented there:
config.settings.SAM_DATA_DIR is a module-level constant fixed at first
import, so mutating HOME after something in-process has already imported
config.settings would silently no-op — a fresh subprocess is the only way
to guarantee a clean import under the HOME being tested.

Deliberately does NOT test settings.primary_model being overridden via
YAML. Separate Phase 4.2 audit finding, out of scope here: Settings.
_select_model() unconditionally overwrites any YAML-configured
primary_model with a RAM-tier default on macOS/Windows (detected_ram_gb is
never None there); Linux currently has no hardware-detection branch in
_detect_hardware() at all, so detected_ram_gb stays None there and a YAML
override survives, but only by accident. That's a config/settings.py
behavior question, not an installer question — reported separately, not
fixed or tested here per this chat's scope (config/settings.py is not to
be modified without a concrete regression).

Never touches the real ~/.sam_data. Binds only to 127.0.0.1.

Usage:
    python3 tests/test_installer_doctor_model_check_offline.py
"""

import http.server
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
results = []


def check(label, condition):
    results.append(bool(condition))
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")


def _serve_tags(models):
    """Start a real loopback HTTP server faking Ollama's /api/tags.
    Binds to port 0 (OS-assigned free port) so parallel test runs never
    collide on a fixed port number."""
    body = json.dumps({"models": [{"name": m} for m in models]}).encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/tags":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):
            pass  # keep test output clean

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _run_doctor(home: Path, ollama_host: str) -> str:
    sam_data = home / ".sam_data"
    sam_data.mkdir(parents=True, exist_ok=True)
    (sam_data / "settings.yaml").write_text(f"ollama_host: {ollama_host}\n")
    result = subprocess.run(
        [sys.executable, "sam_cli.py", "doctor"],
        cwd=str(REPO_ROOT),
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout + result.stderr


def test_configured_model_present_reports_pass():
    httpd = _serve_tags(["qwen2.5:14b", "nomic-embed-text"])
    port = httpd.server_address[1]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = _run_doctor(Path(tmp), f"http://127.0.0.1:{port}")
            check(
                "reports PASS for the default configured model when it IS pulled",
                "Configured model" in out and "qwen2.5:14b" in out and "PASS" in out,
            )
    finally:
        httpd.shutdown()


def test_configured_model_absent_reports_fail_with_pull_hint():
    httpd = _serve_tags(["llama2:7b"])  # default configured model deliberately absent
    port = httpd.server_address[1]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = _run_doctor(Path(tmp), f"http://127.0.0.1:{port}")
            check(
                "reports FAIL when the configured model is NOT among pulled models",
                "Configured model" in out and "FAIL" in out,
            )
            check(
                "FAIL message includes an actionable 'ollama pull' hint",
                "ollama pull qwen2.5:14b" in out,
            )
    finally:
        httpd.shutdown()


def test_ollama_unreachable_reports_unverified_not_false_pass():
    with tempfile.TemporaryDirectory() as tmp:
        # Nothing listening on this port -> connection refused, same as a
        # real machine where Ollama isn't running.
        out = _run_doctor(Path(tmp), "http://127.0.0.1:1")
        check(
            "reports Ollama unreachable as FAIL, not a silent skip",
            "Ollama running" in out and "not reachable" in out,
        )
        check(
            "reports the model check as UNVERIFIED rather than a false PASS",
            "UNVERIFIED" in out and "Configured model" in out,
        )


def main():
    print("=== Doctor configured-model check (Phase 4.2) ===")
    test_configured_model_present_reports_pass()
    test_configured_model_absent_reports_fail_with_pull_hint()
    test_ollama_unreachable_reports_unverified_not_false_pass()
    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("All doctor configured-model checks passed.")


if __name__ == "__main__":
    main()
