"""
SIH26117 — document trust boundary and network egress evidence.
See document_trust.py: extracted document content is data to analyze,
never an instruction to follow. See network_guard.py: technically
defensible proof of local-only network behavior during a task run.
"""

from .document_trust import UNTRUSTED_DOCUMENT_INSTRUCTION, wrap_untrusted
from .network_guard import (
    NetworkGuardReport,
    NetworkPolicyViolation,
    SocketGuard,
    snapshot_connections,
    write_evidence_log,
)

__all__ = [
    "UNTRUSTED_DOCUMENT_INSTRUCTION",
    "wrap_untrusted",
    "NetworkGuardReport",
    "NetworkPolicyViolation",
    "SocketGuard",
    "snapshot_connections",
    "write_evidence_log",
]
