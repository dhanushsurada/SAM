"""
Offline smoke test for the network egress guard (SIH26117, Milestone 5)
— sovereign/security/network_guard.py.

The blocking tests use a deliberately non-routable/public IP literal
(never a hostname) so nothing here depends on DNS or actual internet
reachability — the point being tested is that SocketGuard raises
NetworkPolicyViolation *before* attempting the real connect at all, not
that the connect itself would eventually fail. The allow-path test uses
a real local TCP server on 127.0.0.1 so it's a genuine, deterministic
end-to-end pass-through rather than an assumption.

Usage:
    HOME=/tmp/sam_smoke_network_guard python3 tests/test_sovereign_network_guard_offline.py
"""

import socket
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Settings  # noqa: E402
from sovereign.security.network_guard import (  # noqa: E402
    NetworkPolicyViolation,
    SocketGuard,
    _default_allowed_hosts,
    snapshot_connections,
    write_evidence_log,
)

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


def _start_local_server():
    """A throwaway TCP server on 127.0.0.1 with an OS-assigned free
    port, so the allow-path test has something real to connect to."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _accept_once():
        try:
            conn, _ = srv.accept()
            conn.close()
        except OSError:
            pass

    t = threading.Thread(target=_accept_once, daemon=True)
    t.start()
    return srv, port


# ─── allowlist ───────────────────────────────────────────────────────────

def test_default_allowed_hosts_include_loopback_and_ollama_host():
    settings = Settings()
    allowed = _default_allowed_hosts(settings)
    check("Loopback IP is allowed", "127.0.0.1" in allowed)
    check("'localhost' is allowed", "localhost" in allowed)
    check("IPv6 loopback is allowed", "::1" in allowed)
    check("The configured ollama_host's hostname is allowed", "localhost" in allowed)  # default ollama_host is http://localhost:11434


def test_sovereign_allowed_hosts_extends_the_allowlist():
    settings = Settings()
    settings.sovereign_allowed_hosts = ["gpu-box.lan"]
    allowed = _default_allowed_hosts(settings)
    check("Explicitly configured extra hosts are included", "gpu-box.lan" in allowed)


# ─── SocketGuard: allow path (real, local, deterministic) ─────────────────

def test_guard_allows_and_passes_through_loopback_connections():
    settings = Settings()
    srv, port = _start_local_server()
    try:
        with SocketGuard(settings, task_label="allow-path-test") as guard:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(2)
            client.connect(("127.0.0.1", port))  # should pass straight through
            client.close()
        report = guard.report()
        check("The loopback connection was recorded", len(report.attempts) == 1)
        check("The loopback connection was marked allowed", report.attempts[0].allowed is True)
        check("external_transmission_count is 0 for a loopback-only run", report.external_transmission_count == 0)
    finally:
        srv.close()


# ─── SocketGuard: block path (deterministic — no real network needed) ─────

def test_guard_blocks_external_connection_before_attempting_it():
    settings = Settings()
    with SocketGuard(settings, task_label="block-path-test") as guard:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect(("8.8.8.8", 80))  # public IP literal — no DNS involved
            check("Blocked external connection raises NetworkPolicyViolation", False)
        except NetworkPolicyViolation:
            check("Blocked external connection raises NetworkPolicyViolation", True)
        except OSError:
            # Would mean the guard let it through to the real OS layer —
            # a real failure of the guard, not an expected outcome.
            check("Blocked external connection raises NetworkPolicyViolation", False)
    report = guard.report()
    check("The blocked attempt was recorded", report.blocked_count == 1)
    check("external_transmission_count stays 0 (blocked, so nothing transmitted)", report.external_transmission_count == 0)


def test_guard_non_blocking_mode_logs_without_raising():
    """Tests the block=False path directly against _handle_connect with
    a stubbed-out real connect, rather than a real network attempt —
    deterministic and fast, and isolates exactly the behavior in
    question (log-but-don't-raise) from real socket/OS timing."""
    settings = Settings()
    guard = SocketGuard(settings, block=False)
    guard._original_connect = lambda sock_self, address: "would-have-connected"
    result = guard._handle_connect(None, ("203.0.113.5", 443))  # TEST-NET-3, non-routable by design
    check("block=False does not raise for a disallowed host", result == "would-have-connected")
    check("block=False still records the attempt as not allowed", guard.attempts[0].allowed is False)


# ─── SocketGuard: restoration + reporting ──────────────────────────────────

def test_guard_restores_connect_after_normal_exit():
    original = socket.socket.connect
    settings = Settings()
    with SocketGuard(settings):
        check("connect is patched while the guard is active", socket.socket.connect is not original)
    check("connect is restored after the guard exits normally", socket.socket.connect is original)


def test_guard_restores_connect_after_exception():
    original = socket.socket.connect
    settings = Settings()
    try:
        with SocketGuard(settings):
            raise ValueError("something unrelated went wrong inside the guarded task")
    except ValueError:
        pass
    check("connect is restored even after an exception inside the guarded block", socket.socket.connect is original)


def test_guard_report_duration_is_nonnegative():
    settings = Settings()
    with SocketGuard(settings) as guard:
        pass
    check("report().duration_seconds is a sane non-negative number", guard.report().duration_seconds >= 0)


# ─── evidence log ───────────────────────────────────────────────────────

def test_write_evidence_log_creates_dedicated_jsonl_file():
    settings = Settings()
    settings.sovereign_network_log = str(Path(tempfile.mkdtemp()) / "network_guard.jsonl")
    with SocketGuard(settings, task_label="evidence-log-test") as guard:
        pass
    path = write_evidence_log(guard.report(), settings)
    check("write_evidence_log writes to the dedicated configured path", path == settings.sovereign_network_log)
    check("The evidence log file actually exists", Path(path).exists())

    import json
    line = Path(path).read_text().strip().splitlines()[-1]
    parsed = json.loads(line)
    check("The written line is valid JSON with the expected task_label", parsed["task_label"] == "evidence-log-test")
    check("The written line includes external_transmission_count", "external_transmission_count" in parsed)


def test_write_evidence_log_appends_multiple_runs():
    settings = Settings()
    settings.sovereign_network_log = str(Path(tempfile.mkdtemp()) / "network_guard.jsonl")
    for label in ["run-1", "run-2"]:
        with SocketGuard(settings, task_label=label) as guard:
            pass
        write_evidence_log(guard.report(), settings)
    lines = Path(settings.sovereign_network_log).read_text().strip().splitlines()
    check("Multiple runs append rather than overwrite", len(lines) == 2)


# ─── subprocess-level snapshot (psutil) ────────────────────────────────

def test_snapshot_connections_real_path():
    # psutil is genuinely installed in this sandbox — this exercises the
    # real code path, not a mock.
    result = snapshot_connections()
    check("snapshot_connections returns a list when psutil is available", isinstance(result, list))


def test_snapshot_connections_graceful_without_psutil():
    with patch.dict(sys.modules, {"psutil": None}):
        result = snapshot_connections()
    check("snapshot_connections returns None (not a fabricated empty list) when psutil is unavailable",
          result is None)


def main():
    test_default_allowed_hosts_include_loopback_and_ollama_host()
    test_sovereign_allowed_hosts_extends_the_allowlist()
    test_guard_allows_and_passes_through_loopback_connections()
    test_guard_blocks_external_connection_before_attempting_it()
    test_guard_non_blocking_mode_logs_without_raising()
    test_guard_restores_connect_after_normal_exit()
    test_guard_restores_connect_after_exception()
    test_guard_report_duration_is_nonnegative()
    test_write_evidence_log_creates_dedicated_jsonl_file()
    test_write_evidence_log_appends_multiple_runs()
    test_snapshot_connections_real_path()
    test_snapshot_connections_graceful_without_psutil()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Sovereign Workbench network guard (Milestone 5) verified.")


if __name__ == "__main__":
    main()
