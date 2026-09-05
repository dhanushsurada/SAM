"""
Sovereignty / egress evidence (SIH26117, Milestone 5).

Two complementary layers:

1. SocketGuard — monkey-patches socket.socket.connect for the duration
   of a `with` block, so the SAM process itself is structurally
   prevented from reaching any host outside the allowlist (loopback +
   settings.ollama_host's hostname + settings.sovereign_allowed_hosts),
   not just "expected" not to. Every attempt, allowed or blocked, is
   recorded with a timestamp.

2. snapshot_connections() — a psutil-based, system-wide connection
   snapshot. Covers subprocess connections (e.g. Ollama's own server
   process, or a browser-automation child process) that SocketGuard
   can't see, since SocketGuard only intercepts calls made from *this*
   process. Degrades gracefully to None ("not measured") if psutil
   isn't installed, per the project's own rule against fabricating
   metrics — it never fakes an empty-list result.

DNS resolution (socket.getaddrinfo) is not intercepted — only actual
connection attempts are. Establishing a connection is what data
transmission requires; a bare hostname lookup doesn't move document
content anywhere. Deliberate scope boundary, not an oversight.

Unix domain sockets (non-tuple addresses) are always passed through
unlogged — they're inherently local IPC and can't leave the machine.

Evidence is written to its own dedicated, explicit path
(settings.sovereign_network_log) rather than either of the two
ambiguous existing logging conventions found in the Milestone 0 audit
(main.py's relative logs/sam.log vs Settings.log_path, which don't
agree with each other).

Wiring this to automatically wrap every real SAM task run
(main.py / sam_cli.py) is Milestone 6 (feat/e2e-demo) — this milestone
delivers the capability itself, fully tested standalone.
"""

import json
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse


class NetworkPolicyViolation(Exception):
    pass


@dataclass
class ConnectionAttempt:
    host: str
    port: int
    allowed: bool
    timestamp: float


@dataclass
class NetworkGuardReport:
    task_label: str
    started_at: float
    ended_at: float
    attempts: List[ConnectionAttempt] = field(default_factory=list)
    subprocess_connections: Optional[List[dict]] = None  # None = not measured

    @property
    def duration_seconds(self) -> float:
        return self.ended_at - self.started_at

    @property
    def blocked_count(self) -> int:
        return sum(1 for a in self.attempts if not a.allowed)

    @property
    def external_transmission_count(self) -> int:
        """Blocked connections never transmitted anything. This counts
        attempts that were ALLOWED to a non-loopback host — the only way
        this process could actually have sent data out during the run."""
        loopback = {"127.0.0.1", "localhost", "::1"}
        return sum(1 for a in self.attempts if a.allowed and a.host not in loopback)

    def to_dict(self) -> dict:
        return {
            "task_label": self.task_label,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "attempts": [
                {"host": a.host, "port": a.port, "allowed": a.allowed, "timestamp": a.timestamp}
                for a in self.attempts
            ],
            "blocked_count": self.blocked_count,
            "external_transmission_count": self.external_transmission_count,
            "subprocess_connections": self.subprocess_connections,
        }


def _default_allowed_hosts(settings) -> set:
    allowed = {"127.0.0.1", "localhost", "::1"}
    try:
        parsed = urlparse(settings.ollama_host)
        if parsed.hostname:
            allowed.add(parsed.hostname)
    except Exception:
        pass
    for h in getattr(settings, "sovereign_allowed_hosts", None) or []:
        allowed.add(h)
    return allowed


class SocketGuard:
    """Context manager: while active, socket.socket.connect() is
    intercepted process-wide (all threads). Connections to an allowed
    host pass through unchanged; anything else raises
    NetworkPolicyViolation before the real OS-level connect ever
    happens (when block=True, the default) — or is merely logged
    (block=False), for measuring without interrupting a run."""

    def __init__(self, settings, task_label: str = "task", block: bool = True):
        self.settings = settings
        self.task_label = task_label
        self.block = block
        self.allowed_hosts = _default_allowed_hosts(settings)
        self.attempts: List[ConnectionAttempt] = []
        self._original_connect = None
        self.started_at = None
        self.ended_at = None

    def _is_allowed(self, host: str) -> bool:
        return host in self.allowed_hosts

    def _handle_connect(self, sock_self, address):
        if not isinstance(address, tuple):
            # Unix domain socket or similar — inherently local, never leaves the machine.
            return self._original_connect(sock_self, address)

        host = address[0]
        port = address[1] if len(address) > 1 else 0
        allowed = self._is_allowed(host)
        self.attempts.append(ConnectionAttempt(host=host, port=port, allowed=allowed, timestamp=time.time()))

        if not allowed and self.block:
            raise NetworkPolicyViolation(
                f"Blocked outbound connection to {host}:{port} — not in the "
                f"sovereign allowlist {sorted(self.allowed_hosts)}"
            )
        return self._original_connect(sock_self, address)

    def __enter__(self):
        self.started_at = time.time()
        self._original_connect = socket.socket.connect
        guard = self

        def _patched_connect(sock_self, address):
            return guard._handle_connect(sock_self, address)

        socket.socket.connect = _patched_connect
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        socket.socket.connect = self._original_connect
        self.ended_at = time.time()
        return False  # never swallow exceptions from the guarded task

    def report(self) -> NetworkGuardReport:
        return NetworkGuardReport(
            task_label=self.task_label,
            started_at=self.started_at or time.time(),
            ended_at=self.ended_at or time.time(),
            attempts=list(self.attempts),
        )


def snapshot_connections() -> Optional[List[dict]]:
    """System-wide snapshot via psutil — sees subprocess connections
    that SocketGuard can't. Returns None (never a fabricated empty
    list) if psutil isn't installed."""
    try:
        import psutil
    except ImportError:
        return None

    conns = []
    for c in psutil.net_connections(kind="inet"):
        if c.status == psutil.CONN_LISTEN or not c.raddr:
            continue
        conns.append({
            "pid": c.pid, "raddr_ip": c.raddr.ip, "raddr_port": c.raddr.port, "status": c.status,
        })
    return conns


def write_evidence_log(report: NetworkGuardReport, settings) -> str:
    """Appends one JSON line per guarded run to a dedicated, explicit
    log path — not either of the two ambiguous existing logging
    conventions found during the Milestone 0 audit."""
    log_path = Path(settings.sovereign_network_log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(report.to_dict()) + "\n")
    return str(log_path)
